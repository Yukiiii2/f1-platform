"""Read-only, single-source order replay. No telemetry-to-coordinate synthesis."""

from datetime import timezone

from sqlalchemy import cast, func, or_, select
from sqlalchemy.types import Integer

from app import models
from app.schemas.domain import DriverRead, SessionRead, SessionUpdateRead, TeamRead
from app.schemas.replay import (
    ReplayControl,
    ReplayDriver,
    ReplayInterval,
    ReplayLap,
    ReplayPit,
    ReplayPosition,
    SessionReplay,
)

MAX_DRIVERS = 32
MAX_HOLD = 30


def utc(value):
    # SQLite fixture compatibility; PostgreSQL stores aware source times.
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def sampled(db, model, session_id, provider, driver_ids, start, end, max_samples):
    """Keep first plus latest original row per uniform time bin, in SQL.

    No synthetic timestamps/values. max_samples includes both endpoints.
    Dropped changes are explicitly downsampled; held values expire after 30s.
    """
    duration = (end - start).total_seconds()
    width = max(duration / (max_samples - 2), 0.001)
    if db.get_bind().dialect.name == "sqlite":
        elapsed = (func.julianday(model.timestamp) - func.julianday(start)) * 86400
    else:
        elapsed = func.extract("epoch", model.timestamp) - start.timestamp()
    bucket = cast(elapsed / width, Integer)
    query = select(
        model.id.label("id"),
        func.row_number()
        .over(
            partition_by=(model.driver_id, bucket),
            order_by=(model.timestamp.desc(), model.id),
        )
        .label("bin_row"),
        func.row_number()
        .over(partition_by=model.driver_id, order_by=(model.timestamp, model.id))
        .label("first_row"),
    ).where(
        model.session_id == session_id,
        model.provider == provider,
        model.driver_id.in_(driver_ids),
        model.timestamp >= start,
        model.timestamp <= end,
    )
    if model is models.PositionSample:
        query = query.where(model.position.is_not(None))
    ranked = query.subquery()
    rows = list(
        db.scalars(
            select(model)
            .join(ranked, ranked.c.id == model.id)
            .where(or_(ranked.c.bin_row == 1, ranked.c.first_row == 1))
            .order_by(model.driver_id, model.timestamp, model.id)
        )
    )
    grouped = {}
    for row in rows:
        grouped.setdefault(row.driver_id, []).append(row)
    # Floating boundaries can create an extra bin. Bound before capability
    # detection, so it examines exactly the samples returned to the client.
    return [
        row
        for points in grouped.values()
        for row in (
            points
            if len(points) <= max_samples
            else points[: max_samples - 1] + [points[-1]]
        )
    ]


def session_replay(db, session_id, *, max_samples=300):
    if not 32 <= max_samples <= 600:
        raise ValueError("Replay sampling bound must be 32–600")
    session = db.get(models.Session, session_id)
    if session is None:
        raise LookupError("Session not found")
    event = db.get(models.Event, session.event_id)
    season = db.get(models.Season, event.season_id)
    job = db.scalar(
        select(models.SessionUpdateJob).where(
            models.SessionUpdateJob.session_id == session_id
        )
    )
    provisional = session.status != "completed" or bool(
        job and job.data_status == "provisional"
    )
    payload = SessionReplay(
        session=SessionRead.model_validate(session).model_copy(
            update={"updates": SessionUpdateRead.model_validate(job) if job else None}
        ),
        event_id=event.id,
        event_name=event.name,
        season=season.year,
        provisional=provisional,
    )
    notes = payload.quality.notes
    notes.append(
        "Timing/order replay only. No recorded track coordinates are stored; "
        "markers are not geographic car positions."
    )
    notes.append(
        "Source order samples are held for at most 30 seconds (calculated "
        "playback state), then marked unavailable. "
        "Missing activity does not imply retirement."
    )
    if provisional:
        notes.append(
            "Provisional session records may be corrected; "
            "this is not final race classification."
        )
    if session.type not in {"race", "sprint"}:
        notes.append("Order replay supports recorded race and sprint sessions only.")
        return payload
    # Aggregate first; do not load every raw position/telemetry row or mix sources.
    query = (
        select(
            models.PositionSample.provider,
            models.PositionSample.driver_id,
            func.count(),
            func.min(models.PositionSample.timestamp),
            func.max(models.PositionSample.timestamp),
        )
        .where(
            models.PositionSample.session_id == session_id,
            models.PositionSample.position.is_not(None),
        )
        .group_by(models.PositionSample.provider, models.PositionSample.driver_id)
    )
    groups = list(db.execute(query))
    providers = {}
    for provider, driver_id, count, first, last in groups:
        if count >= 2 and first < last:
            providers.setdefault(provider, []).append(
                (driver_id, count, utc(first), utc(last))
            )
    if not providers:
        notes.append(
            "At least two drivers need multiple timestamped order records. "
            "Core results alone cannot provide replay."
        )
        return payload

    def overlapping_pair(rows):
        ordered = sorted(rows, key=lambda row: (row[2], str(row[0])))
        for index, row in enumerate(ordered):
            for other in ordered[index + 1 :]:
                if other[2] < row[3]:
                    return row, other
        return None

    providers = {
        name: rows for name, rows in providers.items() if overlapping_pair(rows)
    }
    if not providers:
        notes.append(
            "Multi-car replay needs overlapping recorded order coverage "
            "for at least two drivers."
        )
        return payload
    provider = min(providers, key=lambda name: (-len(providers[name]), name))
    scope = sorted(providers[provider], key=lambda row: str(row[0]))
    # Retain the supported pair even when a pathological grid exceeds the bound.
    pair = overlapping_pair(scope)
    selected_ids = {row[0] for row in pair}
    scope = list(pair) + [row for row in scope if row[0] not in selected_ids]
    all_supported = {row[0] for row in scope}
    scope = sorted(scope[:MAX_DRIVERS], key=lambda row: str(row[0]))
    start, end = min(row[2] for row in scope), max(row[3] for row in scope)
    if (end - start).total_seconds() > 21600:
        notes.append("Recorded coverage exceeds the supported six-hour replay window.")
        return payload
    identifiers = [row[0] for row in scope]
    positions = sampled(
        db,
        models.PositionSample,
        session_id,
        provider,
        identifiers,
        start,
        end,
        max_samples,
    )
    # Envelopes can overlap while sparse sample windows never do. Require a
    # usable multi-car instant in the actual bounded representation, with no
    # backwards/future holds and the same expiration rule as the client.
    latest = {}
    simultaneous = False
    for point in sorted(positions, key=lambda row: (utc(row.timestamp), str(row.id))):
        stamp = utc(point.timestamp)
        if any(
            driver != point.driver_id and (stamp - time).total_seconds() <= MAX_HOLD
            for driver, time in latest.items()
        ):
            simultaneous = True
            break
        latest[point.driver_id] = stamp
    if not simultaneous:
        notes.append("Recorded gaps leave no usable overlapping multi-car samples.")
        return payload
    intervals = sampled(
        db,
        models.IntervalSample,
        session_id,
        provider,
        identifiers,
        start,
        end,
        max_samples,
    )
    interval_counts = dict(
        db.execute(
            select(models.IntervalSample.driver_id, func.count())
            .where(
                models.IntervalSample.session_id == session_id,
                models.IntervalSample.provider == provider,
                models.IntervalSample.driver_id.in_(identifiers),
                models.IntervalSample.timestamp >= start,
                models.IntervalSample.timestamp <= end,
            )
            .group_by(models.IntervalSample.driver_id)
        ).all()
    )
    payload.starts_at, payload.ends_at, payload.provider = start, end, provider
    payload.duration_seconds = (end - start).total_seconds()
    payload.quality.sampling_seconds = payload.duration_seconds / (max_samples - 2)
    driver_rows = {
        row.id: row
        for row in db.scalars(
            select(models.Driver).where(models.Driver.id.in_(identifiers))
        )
    }
    results = list(
        db.scalars(select(models.Result).where(models.Result.session_id == session_id))
    )
    teams = {
        row.id: row
        for row in db.scalars(
            select(models.Team).where(
                models.Team.id.in_([row.team_id for row in results])
            )
        )
    }
    team_ids = {row.driver_id: row.team_id for row in results}
    # Per-driver bounded context via a single window query per collection.
    context = {}
    for model, order, bound in (
        (models.Lap, "lap_number", 200),
        (models.PitStop, "timestamp", 50),
    ):
        rank = func.row_number().over(
            partition_by=model.driver_id, order_by=(getattr(model, order), model.id)
        )
        ranked = (
            select(model.id.label("id"), rank.label("row_number"))
            .where(
                model.session_id == session_id,
                model.provider == provider,
                model.driver_id.in_(identifiers),
            )
            .subquery()
        )
        rows = list(
            db.scalars(
                select(model)
                .join(ranked, model.id == ranked.c.id)
                .where(ranked.c.row_number <= bound + 1)
                .order_by(model.driver_id, getattr(model, order))
            )
        )
        context[model] = rows
    expected = (
        all_supported
        | {row[1] for row in groups if row[0] == provider}
        | set(
            db.scalars(
                select(models.SessionDriverIdentity.driver_id).where(
                    models.SessionDriverIdentity.session_id == session_id,
                    models.SessionDriverIdentity.provider == provider,
                )
            )
        )
        | {row.driver_id for row in results}
    )
    missing = expected - set(identifiers)
    payload.quality.omitted_driver_count = len(missing)
    for driver_id, count, first, last in scope:
        points = [row for row in positions if row.driver_id == driver_id]
        if len(points) > max_samples:
            # Floating bin boundaries can allocate an extra bin; retain endpoints.
            points = points[: max_samples - 1] + [points[-1]]
        gaps = (
            any(
                (utc(b.timestamp) - utc(a.timestamp)).total_seconds() > MAX_HOLD
                for a, b in zip(points, points[1:])
            )
            or first > start
            or (end - last).total_seconds() > MAX_HOLD
        )
        payload.quality.gaps_present |= gaps
        payload.quality.downsampled |= len(points) < count
        team = teams.get(team_ids.get(driver_id))
        entry = ReplayDriver(
            driver=DriverRead.model_validate(driver_rows[driver_id]),
            team=TeamRead.model_validate(team) if team else None,
            source_sample_count=count,
            positions=[
                ReplayPosition(
                    id=row.id,
                    timestamp=utc(row.timestamp),
                    elapsed_seconds=(utc(row.timestamp) - start).total_seconds(),
                    position=row.position,
                )
                for row in points
            ],
        )
        samples = [row for row in intervals if row.driver_id == driver_id]
        payload.quality.downsampled |= len(samples) < interval_counts.get(driver_id, 0)
        if len(samples) > max_samples:
            samples = samples[: max_samples - 1] + [samples[-1]]
        entry.intervals = [
            ReplayInterval(
                timestamp=utc(row.timestamp),
                elapsed_seconds=(utc(row.timestamp) - start).total_seconds(),
                gap_to_leader_seconds=row.gap_to_leader_seconds,
                gap_to_leader_laps=row.gap_to_leader_laps,
            )
            for row in samples
        ]
        for model, bound in ((models.Lap, 200), (models.PitStop, 50)):
            rows = [row for row in context[model] if row.driver_id == driver_id]
            payload.quality.truncated_context |= len(rows) > bound
            for row in rows[:bound]:
                if model is models.Lap and row.starts_at is not None:
                    offset = (utc(row.starts_at) - start).total_seconds()
                    entry.laps.append(
                        ReplayLap(
                            lap_number=row.lap_number,
                            starts_at=utc(row.starts_at),
                            start_seconds=offset,
                            end_seconds=offset + float(row.duration_seconds)
                            if row.duration_seconds is not None
                            else None,
                            approximate=row.start_time_is_approximate,
                        )
                    )
                elif model is models.PitStop:
                    entry.pits.append(
                        ReplayPit(
                            timestamp=utc(row.timestamp),
                            elapsed_seconds=(
                                utc(row.timestamp) - start
                            ).total_seconds(),
                            lane_duration_seconds=row.lane_duration_seconds,
                            lap_number=row.lap_number,
                        )
                    )
        payload.drivers.append(entry)
    controls = list(
        db.scalars(
            select(models.RaceControlMessage)
            .where(
                models.RaceControlMessage.session_id == session_id,
                models.RaceControlMessage.provider == provider,
                models.RaceControlMessage.timestamp >= start,
                models.RaceControlMessage.timestamp <= end,
            )
            .order_by(models.RaceControlMessage.timestamp, models.RaceControlMessage.id)
            .limit(201)
        )
    )
    payload.quality.truncated_context |= len(controls) > 200
    payload.race_control = [
        ReplayControl(
            id=row.id,
            timestamp=utc(row.timestamp),
            elapsed_seconds=(utc(row.timestamp) - start).total_seconds(),
            message=row.message[:500],
            category=row.category,
            flag=row.flag,
            scope=row.scope,
            driver_id=row.driver_id,
            lap_number=row.lap_number,
        )
        for row in controls[:200]
    ]
    payload.capability = (
        "partial"
        if provisional
        or payload.quality.gaps_present
        or payload.quality.omitted_driver_count
        or payload.quality.truncated_context
        else "available"
    )
    if payload.quality.downsampled:
        notes.append(
            "Downsampled recorded timing/order: intermediate changes may be omitted; "
            "no synthetic samples were created."
        )
    if payload.quality.gaps_present:
        notes.append("Recorded coverage contains gaps; replay does not bridge them.")
    if payload.quality.omitted_driver_count:
        notes.append(
            "Only replay-supported drivers are shown; this is not a complete grid."
        )
    if payload.quality.truncated_context:
        notes.append(
            "Lap, pit or race-control context is truncated "
            "at the documented payload bound."
        )
    return payload

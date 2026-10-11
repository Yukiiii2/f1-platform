"""Preset validation and batched rehydration; existing analysis stays authoritative."""

from datetime import timezone
from urllib.parse import urlencode
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import case, func, select

from app import models
from app.domain.enums import SessionStatus, SessionType
from app.schemas.comparisons import (
    ComparisonCreate,
    ComparisonRead,
    StrategyConfiguration,
    TelemetryConfiguration,
    UnavailableConfiguration,
)


class InvalidComparison(ValueError):
    pass


def resolve(db, configurations):
    """Bounded lists resolve each identity kind once, not once per saved row."""
    fields = {
        models.Season: lambda c: [c.season],
        models.Event: lambda c: [c.event_id],
        models.Session: lambda c: [c.session_id],
        models.Driver: lambda c: [c.driver_a_id, c.driver_b_id],
        models.Lap: lambda c: (
            [c.lap_a_id, c.lap_b_id] if isinstance(c, TelemetryConfiguration) else []
        ),
    }
    refs = {}
    for model, keys in fields.items():
        ids = {key for config in configurations for key in keys(config)}
        column = model.year if model is models.Season else model.id
        refs[model] = (
            {
                getattr(row, column.key): row
                for row in db.scalars(select(model).where(column.in_(ids)))
            }
            if ids
            else {}
        )
    sessions = {
        c.session_id for c in configurations if isinstance(c, StrategyConfiguration)
    }
    strategies = set()
    for model in (models.Lap, models.Stint, models.PitStop):
        if sessions:
            strategies.update(
                db.execute(
                    select(model.session_id, model.driver_id, model.provider)
                    .where(model.session_id.in_(sessions))
                    .distinct()
                ).all()
            )
    refs["strategies"] = strategies
    all_sessions = {config.session_id for config in configurations}
    refs["provisional"] = (
        set(
            db.scalars(
                select(models.SessionUpdateJob.session_id).where(
                    models.SessionUpdateJob.session_id.in_(all_sessions),
                    models.SessionUpdateJob.data_status == "provisional",
                )
            )
        )
        if all_sessions
        else set()
    )
    # Aggregate coverage metadata only; never load all telemetry traces for a list.
    lap_ids = set(refs[models.Lap])
    sample = models.TelemetrySample
    incomplete = (
        sample.speed_kph.is_(None)
        | sample.throttle_percent.is_(None)
        | sample.brake_applied.is_(None)
        | sample.gear.is_(None)
        | sample.rpm.is_(None)
        | sample.drs_state.is_(None)
    )
    refs["channels"] = (
        {
            lap_id: (count, missing)
            for lap_id, count, missing in db.execute(
                select(
                    sample.lap_id,
                    func.count(),
                    func.sum(case((incomplete, 1), else_=0)),
                )
                .where(sample.lap_id.in_(lap_ids))
                .group_by(sample.lap_id)
            )
        }
        if lap_ids
        else {}
    )
    return refs


def reference_error(config, refs):
    season = refs[models.Season].get(config.season)
    event = refs[models.Event].get(config.event_id)
    session = refs[models.Session].get(config.session_id)
    if (
        not season
        or not event
        or not session
        or any(
            key not in refs[models.Driver]
            for key in (config.driver_a_id, config.driver_b_id)
        )
    ):
        return "A saved season, weekend, session or driver is no longer available."
    if event.season_id != season.id or session.event_id != event.id:
        return "Saved records no longer belong to the same season and weekend."
    if isinstance(config, TelemetryConfiguration):
        laps = [
            refs[models.Lap].get(config.lap_a_id),
            refs[models.Lap].get(config.lap_b_id),
        ]
        if any(lap is None for lap in laps):
            return "A saved lap is no longer available. No replacement was selected."
        if any(
            lap.session_id != session.id or lap.driver_id != driver
            for lap, driver in zip(laps, (config.driver_a_id, config.driver_b_id))
        ):
            return "Saved laps no longer match their session and drivers."
        if laps[0].provider != laps[1].provider:
            return "The existing comparison requires laps from the same source."
    else:
        if (
            session.type != SessionType.RACE
            or session.status != SessionStatus.COMPLETED
        ):
            return "The saved strategy requires a recorded completed race."
        if any(
            (session.id, driver, provider) not in refs["strategies"]
            for driver, provider in (
                (config.driver_a_id, config.provider_a),
                (config.driver_b_id, config.provider_b),
            )
        ):
            return "A saved driver strategy has no remaining session records."
    return None


def apply_configuration(db, row, request: ComparisonCreate):
    config = request.configuration
    refs = resolve(db, [config])
    error = reference_error(config, refs)
    if error:
        raise InvalidComparison(error)
    row.season = config.season
    row.season_id = refs[models.Season][config.season].id
    for key in ("event_id", "session_id", "driver_a_id", "driver_b_id"):
        setattr(row, key, getattr(config, key))
    row.lap_a_id = (
        config.lap_a_id if isinstance(config, TelemetryConfiguration) else None
    )
    row.lap_b_id = (
        config.lap_b_id if isinstance(config, TelemetryConfiguration) else None
    )
    row.configuration = config.model_dump(mode="json")
    row.source_route = (
        "/telemetry" if isinstance(config, TelemetryConfiguration) else "/strategy"
    )


def opening_url(config):
    query = {
        "season": config.season,
        "event": config.event_id,
        "session": config.session_id,
    }
    if isinstance(config, TelemetryConfiguration):
        query.update(
            driver_a=config.driver_a_id,
            driver_b=config.driver_b_id,
            lap_a=config.lap_a_id,
            lap_b=config.lap_b_id,
            alignment=config.alignment,
            compare="1",
        )
        if config.allow_approximate:
            query["allow_approximate"] = "1"
        route = "/telemetry"
    else:
        query.update(
            a=f"{config.provider_a}:{config.driver_a_id}",
            b=f"{config.provider_b}:{config.driver_b_id}",
        )
        route = "/strategy"
    return f"{route}?{urlencode(query)}"


def read_many(db, rows):
    configurations = []
    for row in rows:
        try:
            config = ComparisonCreate(
                title=row.title,
                comparison_type=row.comparison_type,
                configuration=row.configuration,
            ).configuration
        except ValidationError:
            snapshot = {}
            for key in (
                "event_id",
                "session_id",
                "driver_a_id",
                "driver_b_id",
                "lap_a_id",
                "lap_b_id",
            ):
                try:
                    snapshot[key] = UUID(str(row.configuration.get(key)))
                except (ValueError, TypeError):
                    snapshot[key] = None
            version = row.configuration.get("version")
            config = UnavailableConfiguration(
                season=row.season,
                version=version if type(version) is int else None,
                **snapshot,
            )
        configurations.append(config)
    refs = resolve(
        db, [c for c in configurations if not isinstance(c, UnavailableConfiguration)]
    )
    output = []
    for row, config in zip(rows, configurations):
        error = (
            (
                "Saved configuration settings or version are no longer supported. "
                "Return to the source page and save a new comparison."
            )
            if isinstance(config, UnavailableConfiguration)
            else reference_error(config, refs)
        )
        event = refs[models.Event].get(config.event_id)
        session = refs[models.Session].get(config.session_id)
        drivers = [
            refs[models.Driver].get(key)
            for key in (config.driver_a_id, config.driver_b_id)
        ]
        laps = (
            [refs[models.Lap].get(key) for key in (config.lap_a_id, config.lap_b_id)]
            if isinstance(config, TelemetryConfiguration)
            else [None, None]
        )
        notices = [error] if error else []
        partial = False
        if not error and isinstance(config, TelemetryConfiguration):
            partial = any(
                lap.starts_at is None
                or lap.duration_seconds is None
                or lap.start_time_is_approximate
                or any(getattr(lap, f"sector_{n}_seconds") is None for n in (1, 2, 3))
                for lap in laps
            )
            if partial:
                notices.append("Some lap timing is missing or estimated.")
            if any(
                refs["channels"].get(lap.id, (0, 0))[0] < 2
                or refs["channels"].get(lap.id, (0, 0))[1]
                for lap in laps
            ):
                partial = True
                notices.append(
                    "Confirmed telemetry is incomplete or unavailable for these laps. "
                    "Estimated windows and available channels are checked when opened."
                )
        if not error and isinstance(config, StrategyConfiguration):
            # A preset asserts recorded selections, never complete strategy coverage.
            partial = True
            notices.append(
                "Recorded strategy selections are available; stint, pit and pace "
                "coverage is checked when opened."
            )
        if not error and (
            session.status != SessionStatus.COMPLETED
            or session.id in refs["provisional"]
        ):
            partial = True
            notices.append("Session records are provisional, not final classification.")

        def aware(stamp):
            return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp

        output.append(
            ComparisonRead(
                id=row.id,
                title=row.title,
                comparison_type=row.comparison_type,
                source_route=row.source_route,
                configuration=config,
                created_at=aware(row.created_at),
                updated_at=aware(row.updated_at),
                event_name=event.name if event else None,
                session_name=session.type.value if session else None,
                driver_a_name=f"{drivers[0].given_name} {drivers[0].family_name}"
                if drivers[0]
                else None,
                driver_b_name=f"{drivers[1].given_name} {drivers[1].family_name}"
                if drivers[1]
                else None,
                lap_a_number=laps[0].lap_number if laps[0] else None,
                lap_b_number=laps[1].lap_number if laps[1] else None,
                availability="unavailable"
                if error
                else "partial"
                if partial
                else "available",
                notices=notices,
                open_url=None if error else opening_url(config),
            )
        )
    return output

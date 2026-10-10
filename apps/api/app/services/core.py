from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import case, func, select, union
from sqlalchemy.orm import Session as DbSession

from app import models
from app.models import (
    ConstructorStanding,
    DriverStanding,
    Event,
    Result,
    Season,
    Session,
)
from app.schemas.domain import SeasonAvailability


def list_entities(db: DbSession, model, limit: int, offset: int, ids=None, year=None):
    query = select(model)
    if ids is not None:
        query = query.where(model.id.in_(ids))
    if year is not None:
        membership = union(
            select(Result.driver_id)
            .join(Session)
            .join(Event)
            .join(Season)
            .where(Season.year == year),
            select(DriverStanding.driver_id).join(Season).where(Season.year == year),
        )
        query = query.where(model.id.in_(membership))
    return list(db.scalars(query.order_by(model.id).limit(limit).offset(offset)))


def season_availability(db: DbSession, years: list[int]):
    """Bounded batched coverage of persisted core data, never telemetry coverage."""
    seasons = list(db.scalars(select(Season).where(Season.year.in_(years))))
    output = {year: SeasonAvailability(year=year) for year in years}
    if not seasons:
        return output
    ids = [row.id for row in seasons]
    events = list(db.scalars(select(Event).where(Event.season_id.in_(ids))))
    races_with_results = set(
        db.scalars(
            select(Event.id)
            .join(Session)
            .join(Result)
            .where(Event.season_id.in_(ids), Session.type == "race")
            .distinct()
        )
    )
    # One grouped query per category, not one query per driver or season.
    coverage = []
    for model in (DriverStanding, ConstructorStanding):
        coverage.append(
            dict(
                db.execute(
                    select(model.season_id, func.max(Event.round))
                    .join(Event, model.event_id == Event.id)
                    .where(model.season_id.in_(ids))
                    .group_by(model.season_id)
                ).all()
            )
        )
    imports = {
        row[0]: (row[1], row[2])
        for row in db.execute(
            select(
                models.ImportRun.season_id,
                func.max(
                    case(
                        (models.ImportRun.external_identifier.like("%:all"), 1), else_=0
                    )
                ),
                func.max(models.ImportRun.finished_at),
            )
            .where(
                models.ImportRun.season_id.in_(ids),
                models.ImportRun.provider == "jolpica",
                models.ImportRun.status == "succeeded",
            )
            .group_by(models.ImportRun.season_id)
        )
    }
    today = datetime.now(timezone.utc).date()
    for season in seasons:
        calendar = [event for event in events if event.season_id == season.id]
        past = [
            event
            for event in calendar
            if (
                event.scheduled_date
                or (event.starts_at.date() if event.starts_at else today)
            )
            <= today
        ]
        last_round = max((event.round for event in past), default=0)
        driver_coverage = coverage[0].get(season.id, 0)
        team_coverage = coverage[1].get(season.id, 0)
        whole_season, last = imports.get(season.id, (False, None))
        complete = (
            bool(calendar)
            and whole_season
            and all(event.id in races_with_results for event in past)
            and (not past or driver_coverage >= last_round)
            and (not past or team_coverage >= last_round)
        )
        if last and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        output[season.year] = SeasonAvailability(
            year=season.year,
            season_id=season.id,
            availability="imported"
            if complete
            else "partial"
            if calendar
            else "unavailable",
            event_count=len(calendar),
            result_event_count=sum(
                event.id in races_with_results for event in calendar
            ),
            driver_standings_available=bool(driver_coverage),
            constructor_standings_available=bool(team_coverage),
            last_imported_at=last,
        )
    return output


def list_events(db: DbSession, year: int | None, limit: int, offset: int):
    query = select(Event).join(Season)
    if year is not None:
        query = query.where(Season.year == year)
    return list(
        db.scalars(
            query.order_by(Season.year.desc(), Event.round, Event.id)
            .limit(limit)
            .offset(offset)
        )
    )


def event_sessions(db: DbSession, event_id: UUID, limit: int, offset: int):
    query = select(Session).where(Session.event_id == event_id)
    return list(
        db.scalars(
            query.order_by(
                Session.scheduled_date.asc().nulls_last(),
                Session.starts_at.asc().nulls_last(),
                Session.id,
            )
            .limit(limit)
            .offset(offset)
        )
    )


def session_results(db: DbSession, session_id: UUID, limit: int, offset: int):
    query = select(Result).where(Result.session_id == session_id)
    return list(
        db.scalars(
            query.order_by(Result.position.asc().nulls_last(), Result.id)
            .limit(limit)
            .offset(offset)
        )
    )


def standings(
    db: DbSession,
    constructor: bool,
    year: int,
    event_id: UUID | None,
    limit: int,
    offset: int,
):
    model = ConstructorStanding if constructor else DriverStanding
    if event_id is None:
        event_id = db.scalar(
            select(Event.id)
            .join(model, model.event_id == Event.id)
            .join(Season, Event.season_id == Season.id)
            .where(Season.year == year)
            .order_by(Event.round.desc())
            .limit(1)
        )
        if event_id is None:
            return []
    query = (
        select(model)
        .join(Season, model.season_id == Season.id)
        .where(Season.year == year, model.event_id == event_id)
    )
    return list(
        db.scalars(
            query.order_by(model.position.asc().nulls_last(), model.id)
            .limit(limit)
            .offset(offset)
        )
    )

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import (
    ConstructorStanding,
    DriverStanding,
    Event,
    Result,
    Season,
    Session,
)


def list_entities(db: DbSession, model, limit: int, offset: int, ids=None):
    query = select(model)
    if ids is not None:
        query = query.where(model.id.in_(ids))
    return list(db.scalars(query.order_by(model.id).limit(limit).offset(offset)))


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

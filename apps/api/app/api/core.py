from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DbSession

from app import models, schemas
from app.db.session import get_db
from app.services import core

router = APIRouter(tags=["core"])


def database():
    try:
        yield from get_db()
    except (RuntimeError, SQLAlchemyError, ValidationError) as error:
        raise HTTPException(
            status_code=503, detail="Application database is unavailable"
        ) from error


Database = Annotated[DbSession, Depends(database)]
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0)]
Year = Annotated[int, Query(ge=1950)]


def require(db, model, identifier):
    row = db.get(model, identifier)
    if row is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return row


@router.get("/seasons", response_model=list[schemas.SeasonRead])
def seasons(db: Database, limit: Limit = 50, offset: Offset = 0):
    return list(
        db.scalars(
            select(models.Season)
            .order_by(models.Season.year.desc())
            .limit(limit)
            .offset(offset)
        )
    )


@router.get("/events", response_model=list[schemas.EventRead])
def events(
    db: Database, season: Year | None = None, limit: Limit = 50, offset: Offset = 0
):
    return core.list_events(db, season, limit, offset)


@router.get("/events/{event_id}", response_model=schemas.EventRead)
def event(db: Database, event_id: UUID):
    return require(db, models.Event, event_id)


@router.get("/events/{event_id}/sessions", response_model=list[schemas.SessionRead])
def sessions(db: Database, event_id: UUID, limit: Limit = 50, offset: Offset = 0):
    require(db, models.Event, event_id)
    return core.event_sessions(db, event_id, limit, offset)


@router.get("/sessions/{session_id}", response_model=schemas.SessionRead)
def session(db: Database, session_id: UUID):
    return require(db, models.Session, session_id)


@router.get("/sessions/{session_id}/results", response_model=list[schemas.ResultRead])
def results(db: Database, session_id: UUID, limit: Limit = 50, offset: Offset = 0):
    require(db, models.Session, session_id)
    return core.session_results(db, session_id, limit, offset)


@router.get("/circuits", response_model=list[schemas.CircuitRead])
def circuits(db: Database, limit: Limit = 50, offset: Offset = 0):
    return core.list_entities(db, models.Circuit, limit, offset)


@router.get("/circuits/{circuit_id}", response_model=schemas.CircuitRead)
def circuit(db: Database, circuit_id: UUID):
    return require(db, models.Circuit, circuit_id)


@router.get("/drivers", response_model=list[schemas.DriverRead])
def drivers(db: Database, limit: Limit = 50, offset: Offset = 0):
    return core.list_entities(db, models.Driver, limit, offset)


@router.get("/drivers/{driver_id}", response_model=schemas.DriverRead)
def driver(db: Database, driver_id: UUID):
    return require(db, models.Driver, driver_id)


@router.get("/teams", response_model=list[schemas.TeamRead])
def teams(db: Database, limit: Limit = 50, offset: Offset = 0):
    return core.list_entities(db, models.Team, limit, offset)


@router.get("/teams/{team_id}", response_model=schemas.TeamRead)
def team(db: Database, team_id: UUID):
    return require(db, models.Team, team_id)


def require_snapshot_event(db: DbSession, event_id: UUID | None, year: int):
    if event_id is not None:
        event = require(db, models.Event, event_id)
        if db.get(models.Season, event.season_id).year != year:
            raise HTTPException(
                status_code=404, detail="Event is not in the requested season"
            )


@router.get("/standings/drivers", response_model=list[schemas.DriverStandingRead])
def driver_standings(
    db: Database,
    season: Year,
    event_id: UUID | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    require_snapshot_event(db, event_id, season)
    return core.standings(db, False, season, event_id, limit, offset)


@router.get(
    "/standings/constructors", response_model=list[schemas.ConstructorStandingRead]
)
def constructor_standings(
    db: Database,
    season: Year,
    event_id: UUID | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    require_snapshot_event(db, event_id, season)
    return core.standings(db, True, season, event_id, limit, offset)

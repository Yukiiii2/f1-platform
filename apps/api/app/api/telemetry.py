from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import AwareDatetime
from sqlalchemy import select

from app import models
from app.api.core import Database, Limit, Offset, require
from app.schemas import telemetry as schemas
from app.services.telemetry import session_records
from app.telemetry.tyres import tyre_age

router = APIRouter(tags=["telemetry"])
Provider = Annotated[str, Query(min_length=1, max_length=50)]


@router.get("/sessions/{session_id}/laps", response_model=list[schemas.LapRead])
def laps(
    db: Database,
    session_id: UUID,
    driver_id: UUID | None = None,
    provider: Provider | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    require(db, models.Session, session_id)
    return session_records(
        db, models.Lap, session_id, "lap_number", limit, offset, driver_id, provider
    )


@router.get("/laps/{lap_id}", response_model=schemas.LapRead)
def lap(db: Database, lap_id: UUID):
    return require(db, models.Lap, lap_id)


@router.get(
    "/laps/{lap_id}/telemetry", response_model=list[schemas.TelemetrySampleRead]
)
def lap_telemetry(db: Database, lap_id: UUID, limit: Limit = 50, offset: Offset = 0):
    require(db, models.Lap, lap_id)
    return list(
        db.scalars(
            select(models.TelemetrySample)
            .where(models.TelemetrySample.lap_id == lap_id)
            .order_by(models.TelemetrySample.timestamp, models.TelemetrySample.id)
            .limit(limit)
            .offset(offset)
        )
    )


@router.get(
    "/sessions/{session_id}/telemetry", response_model=list[schemas.TelemetrySampleRead]
)
def telemetry(
    db: Database,
    session_id: UUID,
    driver_id: UUID | None = None,
    provider: Provider | None = None,
    from_time: AwareDatetime | None = None,
    to_time: AwareDatetime | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    require(db, models.Session, session_id)
    if from_time is not None and to_time is not None and to_time <= from_time:
        raise HTTPException(status_code=422, detail="to_time must be after from_time")
    return session_records(
        db,
        models.TelemetrySample,
        session_id,
        "timestamp",
        limit,
        offset,
        driver_id,
        provider,
        from_time,
        to_time,
    )


@router.get("/sessions/{session_id}/stints", response_model=list[schemas.StintRead])
def stints(
    db: Database,
    session_id: UUID,
    driver_id: UUID | None = None,
    provider: Provider | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    require(db, models.Session, session_id)
    return session_records(
        db, models.Stint, session_id, "stint_number", limit, offset, driver_id, provider
    )


@router.get("/stints/{stint_id}/tyre-age", response_model=schemas.TyreAgeRead)
def stint_tyre_age(
    db: Database, stint_id: UUID, completed_lap: Annotated[int, Query(ge=0)]
):
    stint = require(db, models.Stint, stint_id)
    if stint.lap_start is None:
        raise HTTPException(status_code=422, detail="Stint start lap is unavailable")
    try:
        usage, total = tyre_age(
            stint.tyre_age_at_start, stint.lap_start, stint.lap_end, completed_lap
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return schemas.TyreAgeRead(
        stint_id=stint.id,
        completed_lap=completed_lap,
        tyre_age_at_start=stint.tyre_age_at_start,
        completed_laps_on_stint=usage,
        total_tyre_age=total,
    )


@router.get("/sessions/{session_id}/pits", response_model=list[schemas.PitStopRead])
def pits(
    db: Database,
    session_id: UUID,
    driver_id: UUID | None = None,
    provider: Provider | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    require(db, models.Session, session_id)
    return session_records(
        db, models.PitStop, session_id, "timestamp", limit, offset, driver_id, provider
    )


@router.get(
    "/sessions/{session_id}/positions", response_model=list[schemas.PositionSampleRead]
)
def positions(
    db: Database,
    session_id: UUID,
    driver_id: UUID | None = None,
    provider: Provider | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    require(db, models.Session, session_id)
    return session_records(
        db,
        models.PositionSample,
        session_id,
        "timestamp",
        limit,
        offset,
        driver_id,
        provider,
    )


@router.get(
    "/sessions/{session_id}/intervals", response_model=list[schemas.IntervalSampleRead]
)
def intervals(
    db: Database,
    session_id: UUID,
    driver_id: UUID | None = None,
    provider: Provider | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    require(db, models.Session, session_id)
    return session_records(
        db,
        models.IntervalSample,
        session_id,
        "timestamp",
        limit,
        offset,
        driver_id,
        provider,
    )


@router.get(
    "/sessions/{session_id}/race-control",
    response_model=list[schemas.RaceControlMessageRead],
)
def race_control(
    db: Database,
    session_id: UUID,
    driver_id: UUID | None = None,
    provider: Provider | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    require(db, models.Session, session_id)
    return session_records(
        db,
        models.RaceControlMessage,
        session_id,
        "timestamp",
        limit,
        offset,
        driver_id,
        provider,
    )


@router.get(
    "/sessions/{session_id}/weather", response_model=list[schemas.WeatherSampleRead]
)
def weather(
    db: Database,
    session_id: UUID,
    provider: Provider | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    require(db, models.Session, session_id)
    return session_records(
        db,
        models.WeatherSample,
        session_id,
        "timestamp",
        limit,
        offset,
        provider=provider,
    )

from uuid import UUID

from fastapi import APIRouter, HTTPException

from app import models
from app.api.core import Database, require
from app.api.telemetry import Provider
from app.domain.enums import SessionStatus, SessionType
from app.schemas.strategy import StrategyRead
from app.services.strategy import session_strategy

router = APIRouter(tags=["strategy"])


@router.get("/sessions/{session_id}/strategy", response_model=StrategyRead)
def strategy(db: Database, session_id: UUID, provider: Provider | None = None):
    session = require(db, models.Session, session_id)
    if session.type != SessionType.RACE or session.status != SessionStatus.COMPLETED:
        raise HTTPException(
            status_code=422, detail="Strategy requires a recorded completed race"
        )
    return session_strategy(db, session, provider)

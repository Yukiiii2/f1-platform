from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app import models
from app.api.core import Database, require
from app.schemas.replay import SessionReplay
from app.services.replay import session_replay

router = APIRouter(tags=["replay"])


@router.get("/sessions/{session_id}/replay", response_model=SessionReplay)
def replay(
    db: Database,
    session_id: UUID,
    max_samples: Annotated[int, Query(ge=32, le=600)] = 300,
):
    require(db, models.Session, session_id)
    return session_replay(db, session_id, max_samples=max_samples)

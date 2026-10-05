from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.core import router as core_router

router = APIRouter(prefix="/v1")
router.include_router(core_router)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Process liveness only; does not assert database readiness."""
    return HealthResponse()

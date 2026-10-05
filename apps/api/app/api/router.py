from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.core import router as core_router
from app.api.telemetry import router as telemetry_router

router = APIRouter(prefix="/v1")
router.include_router(core_router)
router.include_router(telemetry_router)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Process liveness only; does not assert database readiness."""
    return HealthResponse()

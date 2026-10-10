"""Pitwall backend only: keys and model transport stay server-side."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.ai.client import AIUnavailable, ModelClient
from app.ai.protection import permit
from app.ai.providers import configured_client
from app.ai.service import AnswerError, ContextError, query
from app.api.core import Database
from app.core.config import get_settings
from app.db.session import get_engine
from app.schemas.ai import QueryRequest, QueryResponse


class PitwallRoute(APIRoute):
    """Do not echo question/context input in public validation failures."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def safe_handler(request: Request):
            try:
                return await handler(request)
            except RequestValidationError:
                raise HTTPException(
                    status_code=422, detail="Invalid Pitwall request"
                ) from None

        return safe_handler


router = APIRouter(tags=["ai"], route_class=PitwallRoute)


def ai_client():
    try:
        settings = get_settings()
    except ValidationError:
        raise HTTPException(
            status_code=503, detail="Pitwall configuration is unavailable"
        ) from None
    try:
        with configured_client(settings) as client:
            yield client
    except AIUnavailable:
        raise HTTPException(
            status_code=503, detail="Pitwall model configuration/service is unavailable"
        ) from None


Client = Annotated[ModelClient, Depends(ai_client)]


def pitwall_access():
    try:
        settings = get_settings()
        with get_engine().connect() as connection, permit(connection, settings):
            yield
    except (RuntimeError, SQLAlchemyError, ValidationError):
        raise HTTPException(503, "Pitwall is temporarily unavailable") from None


@router.post(
    "/ai/query", response_model=QueryResponse, dependencies=[Depends(pitwall_access)]
)
def ai_query(db: Database, request: QueryRequest, model: Client):
    try:
        return query(db, request, model)
    except ContextError:
        raise HTTPException(
            status_code=422, detail="Page context is missing or inconsistent"
        ) from None
    except AnswerError:
        raise HTTPException(
            status_code=502,
            detail="Pitwall could not produce an evidence-backed answer; "
            "narrow the question or context",
        ) from None
    except AIUnavailable:
        raise HTTPException(
            status_code=503, detail="Pitwall model service is temporarily unavailable"
        ) from None

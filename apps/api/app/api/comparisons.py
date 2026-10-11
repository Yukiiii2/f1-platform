"""Private user presets; legacy workspace rows require explicit operator assignment."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import models
from app.api.auth import authenticated_owner
from app.api.core import Database, Limit, Offset, Year
from app.schemas.comparisons import ComparisonCreate, ComparisonRead, ComparisonUpdate
from app.services.comparisons import InvalidComparison, apply_configuration, read_many

router = APIRouter(prefix="/comparisons", tags=["saved comparisons"])


Owner = Annotated[UUID, Depends(authenticated_owner)]


def owned(db, identifier, owner):
    row = db.scalar(
        select(models.SavedComparison).where(
            models.SavedComparison.id == identifier,
            models.SavedComparison.user_id == owner,
        )
    )
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Saved comparison not found",
            headers={"Cache-Control": "no-store"},
        )
    return row


def persist(db, row):
    try:
        db.add(row)
        db.commit()
        db.refresh(row)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail="A referenced record changed. Reload the comparison and retry.",
        ) from error
    return read_many(db, [row])[0]


@router.post("", response_model=ComparisonRead, status_code=201)
def create(db: Database, owner: Owner, request: ComparisonCreate):
    row = models.SavedComparison(
        user_id=owner, title=request.title, comparison_type=request.comparison_type
    )
    try:
        apply_configuration(db, row, request)
    except InvalidComparison as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return persist(db, row)


@router.get("", response_model=list[ComparisonRead])
def listing(
    db: Database,
    owner: Owner,
    season: Year | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    query = select(models.SavedComparison).where(
        models.SavedComparison.user_id == owner
    )
    if season is not None:
        query = query.where(models.SavedComparison.season == season)
    rows = db.scalars(
        query.order_by(
            models.SavedComparison.updated_at.desc(), models.SavedComparison.id
        )
        .limit(limit)
        .offset(offset)
    ).all()
    return read_many(db, rows)


@router.get("/{comparison_id}", response_model=ComparisonRead)
def get(db: Database, owner: Owner, comparison_id: UUID):
    return read_many(db, [owned(db, comparison_id, owner)])[0]


@router.patch("/{comparison_id}", response_model=ComparisonRead)
def update(db: Database, owner: Owner, comparison_id: UUID, request: ComparisonUpdate):
    row = owned(db, comparison_id, owner)
    if request.configuration is not None:
        try:
            validated = ComparisonCreate(
                title=request.title or row.title,
                comparison_type=row.comparison_type,
                configuration=request.configuration,
            )
            apply_configuration(db, row, validated)
        except (InvalidComparison, ValidationError) as error:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Saved configuration is unavailable or does not match "
                    "its comparison type"
                ),
            ) from error
    if request.title is not None:
        row.title = request.title
    return persist(db, row)


@router.delete("/{comparison_id}", status_code=204)
def delete(db: Database, owner: Owner, comparison_id: UUID):
    db.delete(owned(db, comparison_id, owner))
    db.commit()
    return Response(status_code=204)

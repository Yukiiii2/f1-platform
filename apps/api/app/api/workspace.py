"""Authenticated organization; every access is owner-scoped, never ID-only."""

from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import models
from app.api.auth import account_user, admission, authenticated_owner
from app.api.core import Database, Limit, Offset
from app.schemas.workspace import (
    CollectionCreate,
    CollectionDetail,
    CollectionRead,
    CollectionUpdate,
    FavoriteCreate,
    ReferenceCreate,
    ReferenceRead,
)
from app.services.workspace import collections_read, references_read, validate_reference

router = APIRouter(tags=["analysis workspace"])
Owner = Annotated[UUID, Depends(authenticated_owner)]


def write_owner(db: Database, request: Request, response: Response):
    return account_user(db, request, response, lock=True).id


Writer = Annotated[UUID, Depends(write_owner)]


def owned(db, model, identifier, owner):
    row = db.scalar(select(model).where(model.id == identifier, model.user_id == owner))
    if row is None:
        raise HTTPException(
            404, "Private record not found", headers={"Cache-Control": "no-store"}
        )
    return row


def commit(db):
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            422,
            "A referenced record changed. Reload and retry.",
            headers={"Cache-Control": "no-store"},
        ) from error


@router.get("/collections", response_model=list[CollectionRead])
def listing(db: Database, owner: Owner, limit: Limit = 50, offset: Offset = 0):
    rows = db.scalars(
        select(models.Collection)
        .where(models.Collection.user_id == owner)
        .order_by(models.Collection.updated_at.desc(), models.Collection.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return collections_read(db, rows)


@router.post(
    "/collections",
    response_model=CollectionRead,
    status_code=201,
    dependencies=[Depends(admission)],
)
def create(db: Database, owner: Writer, request: CollectionCreate):
    row = models.Collection(user_id=owner, **request.model_dump())
    db.add(row)
    commit(db)
    return collections_read(db, [row])[0]


@router.get("/collections/{collection_id}", response_model=CollectionDetail)
def detail(
    db: Database,
    owner: Owner,
    collection_id: UUID,
    limit: Limit = 50,
    offset: Offset = 0,
):
    row = owned(db, models.Collection, collection_id, owner)
    items = db.scalars(
        select(models.CollectionItem)
        .where(models.CollectionItem.collection_id == row.id)
        .order_by(models.CollectionItem.created_at.desc(), models.CollectionItem.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return CollectionDetail(
        **collections_read(db, [row])[0].model_dump(),
        items=references_read(db, items, owner),
    )


@router.patch(
    "/collections/{collection_id}",
    response_model=CollectionRead,
    dependencies=[Depends(admission)],
)
def update(db: Database, owner: Writer, collection_id: UUID, request: CollectionUpdate):
    row = owned(db, models.Collection, collection_id, owner)
    for key, value in request.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    commit(db)
    return collections_read(db, [row])[0]


@router.delete(
    "/collections/{collection_id}", status_code=204, dependencies=[Depends(admission)]
)
def remove(db: Database, owner: Writer, collection_id: UUID):
    db.delete(owned(db, models.Collection, collection_id, owner))
    commit(db)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post(
    "/collections/{collection_id}/items",
    response_model=ReferenceRead,
    status_code=201,
    dependencies=[Depends(admission)],
)
def add(db: Database, owner: Writer, collection_id: UUID, request: ReferenceCreate):
    collection = owned(db, models.Collection, collection_id, owner)
    row = db.scalar(
        select(models.CollectionItem).where(
            models.CollectionItem.collection_id == collection.id,
            models.CollectionItem.reference_type == request.reference_type,
            models.CollectionItem.reference_id == request.reference_id,
            models.CollectionItem.season == request.season,
        )
    )
    # Existing references may now be stale; keep their explicit unavailable state.
    if row is not None:
        return references_read(db, [row], owner)[0]
    row = models.CollectionItem(collection_id=collection.id)
    if not validate_reference(db, row, request, owner):
        raise HTTPException(
            422, "Reference is unavailable or does not match this season"
        )
    collection.updated_at = datetime.now(timezone.utc)
    db.add(row)
    commit(db)
    return references_read(db, [row], owner)[0]


@router.delete(
    "/collections/{collection_id}/items/{item_id}",
    status_code=204,
    dependencies=[Depends(admission)],
)
def remove_item(db: Database, owner: Writer, collection_id: UUID, item_id: UUID):
    collection = owned(db, models.Collection, collection_id, owner)
    row = db.scalar(
        select(models.CollectionItem).where(
            models.CollectionItem.id == item_id,
            models.CollectionItem.collection_id == collection.id,
        )
    )
    if row is None:
        raise HTTPException(
            404, "Private record not found", headers={"Cache-Control": "no-store"}
        )
    db.delete(row)
    collection.updated_at = datetime.now(timezone.utc)
    commit(db)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("/favorites", response_model=list[ReferenceRead])
def favorites(
    db: Database,
    owner: Owner,
    reference_type: Literal["driver", "event"] | None = None,
    reference_id: UUID | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    query = select(models.Favorite).where(models.Favorite.user_id == owner)
    if reference_type:
        query = query.where(models.Favorite.reference_type == reference_type)
    if reference_id:
        query = query.where(models.Favorite.reference_id == reference_id)
    rows = db.scalars(
        query.order_by(models.Favorite.created_at.desc(), models.Favorite.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return references_read(db, rows, owner)


@router.post(
    "/favorites",
    response_model=ReferenceRead,
    status_code=201,
    dependencies=[Depends(admission)],
)
def favorite(db: Database, owner: Writer, request: FavoriteCreate):
    row = db.scalar(
        select(models.Favorite).where(
            models.Favorite.user_id == owner,
            models.Favorite.reference_type == request.reference_type,
            models.Favorite.reference_id == request.reference_id,
        )
    )
    if row is None:
        row = models.Favorite(user_id=owner)
        if not validate_reference(db, row, request, owner):
            raise HTTPException(
                422, "Reference is unavailable or does not match this season"
            )
        db.add(row)
        commit(db)
    return references_read(db, [row], owner)[0]


@router.delete(
    "/favorites/{favorite_id}", status_code=204, dependencies=[Depends(admission)]
)
def unfavorite(db: Database, owner: Writer, favorite_id: UUID):
    db.delete(owned(db, models.Favorite, favorite_id, owner))
    commit(db)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})

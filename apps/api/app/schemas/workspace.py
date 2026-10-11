from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from app.schemas.domain import Schema

ReferenceType = Literal["comparison", "event", "driver", "session"]


class CollectionCreate(Schema):
    title: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)


class CollectionUpdate(Schema):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def nonempty(self):
        if not self.model_fields_set or (
            "title" in self.model_fields_set and self.title is None
        ):
            raise ValueError("Supply a title or description; the title cannot be null")
        return self


class ReferenceCreate(Schema):
    reference_type: ReferenceType
    reference_id: UUID
    season: int = Field(ge=1950, le=9999)


class FavoriteCreate(ReferenceCreate):
    reference_type: Literal["event", "driver"]


class ReferenceRead(ReferenceCreate):
    id: UUID
    created_at: AwareDatetime
    updated_at: AwareDatetime
    label: str
    availability: Literal["available", "partial", "unavailable"]
    notices: list[str]
    open_url: str | None


class CollectionRead(CollectionCreate):
    id: UUID
    created_at: AwareDatetime
    updated_at: AwareDatetime
    item_count: int


class CollectionDetail(CollectionRead):
    items: list[ReferenceRead]

"""Private organization of references; shared race data has no user ownership."""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Entity


class Collection(Entity, Base):
    __tablename__ = "collections"
    __table_args__ = (
        Index("ix_collections_user_updated", "user_id", "updated_at", "id"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(String(1000))


class Reference:
    # Original identity survives SET NULL; it never silently points at a replacement.
    reference_id: Mapped[UUID]
    reference_type: Mapped[str] = mapped_column(String(20))
    season: Mapped[int]
    season_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("seasons.id", ondelete="SET NULL")
    )
    event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("events.id", ondelete="SET NULL")
    )
    driver_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("drivers.id", ondelete="SET NULL")
    )
    session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sessions.id", ondelete="SET NULL")
    )
    comparison_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("saved_comparisons.id", ondelete="SET NULL")
    )


class CollectionItem(Reference, Entity, Base):
    __tablename__ = "collection_items"
    __table_args__ = (
        CheckConstraint(
            "reference_type IN ('comparison','event','driver','session')",
            name="supported_type",
        ),
        CheckConstraint("season >= 1950 AND season <= 9999", name="valid_season"),
        UniqueConstraint(
            "collection_id",
            "reference_type",
            "reference_id",
            "season",
            name="uq_collection_items_reference",
        ),
        Index(
            "ix_collection_items_collection_created",
            "collection_id",
            "created_at",
            "id",
        ),
    )
    collection_id: Mapped[UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE")
    )


class Favorite(Reference, Entity, Base):
    __tablename__ = "favorites"
    __table_args__ = (
        CheckConstraint("reference_type IN ('event','driver')", name="supported_type"),
        CheckConstraint("season >= 1950 AND season <= 9999", name="valid_season"),
        UniqueConstraint(
            "user_id", "reference_type", "reference_id", name="uq_favorites_reference"
        ),
        Index("ix_favorites_user_created", "user_id", "created_at", "id"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

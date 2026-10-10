"""Private core provider provenance; never returned by domain APIs."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Entity


class CoreSourceRevision(Entity, Base):
    __tablename__ = "core_source_revisions"
    __table_args__ = (
        UniqueConstraint(
            "provider", "scope", "content_hash", name="uq_core_source_revision"
        ),
    )

    provider: Mapped[str] = mapped_column(String(50))
    scope: Mapped[str] = mapped_column(String(100))
    content_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CoreSourceState(Base):
    __tablename__ = "core_source_states"

    identity_id: Mapped[UUID] = mapped_column(
        ForeignKey("provider_identities.id"), primary_key=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Entity


class ProviderIdentity(Entity, Base):
    __tablename__ = "provider_identities"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "entity_kind",
            "external_id",
            name="uq_provider_identity_external",
        ),
        UniqueConstraint(
            "provider", "entity_kind", "domain_id", name="uq_provider_identity_domain"
        ),
        CheckConstraint(
            "entity_kind IN ('season', 'circuit', 'event', 'session', 'driver', "
            "'team', 'result', 'driver_standing', 'constructor_standing')",
            name="entity_kind",
        ),
    )

    provider: Mapped[str] = mapped_column(String(50))
    entity_kind: Mapped[str] = mapped_column(String(30))
    external_id: Mapped[str] = mapped_column(String(300))
    domain_id: Mapped[UUID] = mapped_column(index=True)


class ImportRun(Entity, Base):
    __tablename__ = "import_runs"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'succeeded', 'failed')", name="status"),
        CheckConstraint("attempt_count > 0", name="positive_attempt_count"),
    )

    provider: Mapped[str] = mapped_column(String(50), index=True)
    external_identifier: Mapped[str] = mapped_column(String(100))
    season_id: Mapped[UUID | None] = mapped_column(ForeignKey("seasons.id"))
    session_id: Mapped[UUID | None] = mapped_column(ForeignKey("sessions.id"))
    status: Mapped[str] = mapped_column(String(20), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(default=1)
    row_counts: Mapped[dict] = mapped_column(JSON, default=dict)
    failure_details: Mapped[str | None] = mapped_column(String(500))

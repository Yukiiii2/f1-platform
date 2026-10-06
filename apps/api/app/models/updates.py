"""Durable orchestration state, separate from F1 facts and raw source revisions."""

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


class SessionUpdateJob(Entity, Base):
    __tablename__ = "session_update_jobs"
    __table_args__ = (
        UniqueConstraint("session_id", name="uq_session_update_session"),
        UniqueConstraint("source_session", name="uq_session_update_source"),
        CheckConstraint("source_session > 0", name="positive_source_session"),
        CheckConstraint(
            "attempt_count >= 0 AND consecutive_failures >= 0",
            name="nonnegative_attempts",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'retry', 'succeeded', "
            "'failed', 'cancelled')",
            name="status",
        ),
    )

    session_id: Mapped[UUID] = mapped_column(ForeignKey("sessions.id"))
    source_session: Mapped[int]
    driver_ids: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    stage: Mapped[str] = mapped_column(String(30), default="completion")
    attempt_count: Mapped[int] = mapped_column(default=0)
    consecutive_failures: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completion_evidence: Mapped[dict | None] = mapped_column(JSON)
    core_import_id: Mapped[UUID | None] = mapped_column(ForeignKey("import_runs.id"))
    telemetry_import_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("import_runs.id")
    )
    row_counts: Mapped[dict] = mapped_column(JSON, default=dict)
    derived_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    cache_state: Mapped[dict] = mapped_column(JSON, default=dict)
    failure_details: Mapped[str | None] = mapped_column(String(100))

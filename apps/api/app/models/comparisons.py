"""User-owned presets and preserved legacy IDs/settings, never analysis."""

from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Entity


class SavedComparison(Entity, Base):
    __tablename__ = "saved_comparisons"
    __table_args__ = (
        CheckConstraint(
            "comparison_type IN ('telemetry_laps', 'strategy_tyres')",
            name="supported_type",
        ),
        CheckConstraint("season >= 1950", name="valid_season"),
        CheckConstraint(
            "(user_id IS NOT NULL AND owner_id IS NULL) OR "
            "(user_id IS NULL AND owner_id IS NOT NULL)",
            name="one_owner",
        ),
        Index("ix_saved_comparisons_owner_updated", "owner_id", "updated_at", "id"),
        Index("ix_saved_comparisons_owner_season", "owner_id", "season"),
        Index("ix_saved_comparisons_user_updated", "user_id", "updated_at", "id"),
        Index("ix_saved_comparisons_user_season", "user_id", "season"),
    )

    # Retained only for explicit operator assignment of legacy workspace presets.
    owner_id: Mapped[UUID | None]
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    title: Mapped[str] = mapped_column(String(120))
    comparison_type: Mapped[str] = mapped_column(String(30))
    season: Mapped[int]
    source_route: Mapped[str] = mapped_column(String(30))
    configuration: Mapped[dict] = mapped_column(JSON)
    # Preserve the preset on record removal. Original IDs remain in configuration.
    season_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("seasons.id", ondelete="SET NULL")
    )
    event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("events.id", ondelete="SET NULL")
    )
    session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sessions.id", ondelete="SET NULL")
    )
    driver_a_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("drivers.id", ondelete="SET NULL")
    )
    driver_b_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("drivers.id", ondelete="SET NULL")
    )
    lap_a_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("laps.id", ondelete="SET NULL")
    )
    lap_b_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("laps.id", ondelete="SET NULL")
    )

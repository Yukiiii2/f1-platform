from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Entity
from app.domain.enums import SessionStatus, SessionType


class Season(Entity, Base):
    __tablename__ = "seasons"
    __table_args__ = (CheckConstraint("year >= 1950", name="valid_year"),)

    year: Mapped[int] = mapped_column(unique=True)


class Circuit(Entity, Base):
    __tablename__ = "circuits"

    name: Mapped[str] = mapped_column(String(200))
    country: Mapped[str] = mapped_column(String(100))
    locality: Mapped[str | None] = mapped_column(String(100))
    timezone: Mapped[str | None] = mapped_column(String(64))


class Event(Entity, Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("season_id", "round", name="uq_events_season_round"),
        UniqueConstraint("id", "season_id", name="uq_events_id_season"),
        CheckConstraint("round > 0", name="positive_round"),
        CheckConstraint("ends_at >= starts_at", name="time_order"),
    )

    season_id: Mapped[UUID] = mapped_column(ForeignKey("seasons.id"), index=True)
    circuit_id: Mapped[UUID] = mapped_column(ForeignKey("circuits.id"), index=True)
    round: Mapped[int]
    name: Mapped[str] = mapped_column(String(200))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_date: Mapped[date | None]
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Session(Entity, Base):
    __tablename__ = "sessions"
    __table_args__ = (
        UniqueConstraint("event_id", "type", name="uq_sessions_event_type"),
        CheckConstraint("ends_at >= starts_at", name="time_order"),
    )

    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id"), index=True)
    type: Mapped[SessionType] = mapped_column(
        Enum(
            SessionType,
            values_callable=lambda enum: [item.value for item in enum],
            native_enum=False,
            create_constraint=True,
            name="session_type",
        )
    )
    status: Mapped[SessionStatus] = mapped_column(
        Enum(
            SessionStatus,
            values_callable=lambda enum: [item.value for item in enum],
            native_enum=False,
            create_constraint=True,
            name="session_status",
        ),
        default=SessionStatus.UNKNOWN,
    )
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_date: Mapped[date | None]


class Driver(Entity, Base):
    __tablename__ = "drivers"
    __table_args__ = (
        CheckConstraint("permanent_number BETWEEN 1 AND 99", name="number_range"),
    )

    given_name: Mapped[str] = mapped_column(String(100))
    family_name: Mapped[str] = mapped_column(String(100))
    code: Mapped[str | None] = mapped_column(String(3))
    permanent_number: Mapped[int | None]
    nationality: Mapped[str | None] = mapped_column(String(100))


class Team(Entity, Base):
    __tablename__ = "teams"

    name: Mapped[str] = mapped_column(String(200))
    nationality: Mapped[str | None] = mapped_column(String(100))


class Result(Entity, Base):
    __tablename__ = "results"
    __table_args__ = (
        UniqueConstraint("session_id", "driver_id", name="uq_results_session_driver"),
        CheckConstraint("position > 0", name="positive_position"),
        CheckConstraint("grid_position >= 0", name="nonnegative_grid"),
        CheckConstraint("points >= 0", name="nonnegative_points"),
        CheckConstraint("completed_laps >= 0", name="nonnegative_laps"),
        CheckConstraint("total_time_ms > 0", name="positive_time"),
        CheckConstraint("gap_ms >= 0", name="nonnegative_gap"),
    )

    session_id: Mapped[UUID] = mapped_column(ForeignKey("sessions.id"), index=True)
    driver_id: Mapped[UUID] = mapped_column(ForeignKey("drivers.id"), index=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    position: Mapped[int | None]
    grid_position: Mapped[int | None]
    points: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    completed_laps: Mapped[int | None]
    status: Mapped[str | None] = mapped_column(String(100))
    total_time_ms: Mapped[int | None]
    gap_ms: Mapped[int | None]


class DriverStanding(Entity, Base):
    __tablename__ = "driver_standings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "season_id"],
            ["events.id", "events.season_id"],
            name="fk_driver_standings_event_season",
        ),
        UniqueConstraint(
            "event_id", "driver_id", name="uq_driver_standings_event_driver"
        ),
        CheckConstraint("position > 0", name="positive_position"),
        CheckConstraint("points >= 0", name="nonnegative_points"),
        CheckConstraint("wins >= 0", name="nonnegative_wins"),
    )

    season_id: Mapped[UUID] = mapped_column(ForeignKey("seasons.id"), index=True)
    event_id: Mapped[UUID] = mapped_column(index=True)
    driver_id: Mapped[UUID] = mapped_column(ForeignKey("drivers.id"), index=True)
    position: Mapped[int | None]
    points: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    wins: Mapped[int]


class ConstructorStanding(Entity, Base):
    __tablename__ = "constructor_standings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "season_id"],
            ["events.id", "events.season_id"],
            name="fk_constructor_standings_event_season",
        ),
        UniqueConstraint(
            "event_id", "team_id", name="uq_constructor_standings_event_team"
        ),
        CheckConstraint("position > 0", name="positive_position"),
        CheckConstraint("points >= 0", name="nonnegative_points"),
        CheckConstraint("wins >= 0", name="nonnegative_wins"),
    )

    season_id: Mapped[UUID] = mapped_column(ForeignKey("seasons.id"), index=True)
    event_id: Mapped[UUID] = mapped_column(index=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    position: Mapped[int | None]
    points: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    wins: Mapped[int]

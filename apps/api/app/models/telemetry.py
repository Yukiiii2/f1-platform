"""Provider-independent session data; raw revisions live in a separate ledger."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Entity


class TelemetrySourceRecord(Entity, Base):
    __tablename__ = "telemetry_source_records"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "session_id",
            "kind",
            "source_key",
            "checksum",
            name="uq_telemetry_source_revision",
        ),
    )

    provider: Mapped[str] = mapped_column(String(50))
    session_id: Mapped[UUID] = mapped_column(ForeignKey("sessions.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    source_key: Mapped[str] = mapped_column(String(200))
    checksum: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SessionDriverIdentity(Entity, Base):
    """Car numbers are scoped to a provider session, never permanent driver IDs."""

    __tablename__ = "session_driver_identities"
    __table_args__ = (
        UniqueConstraint(
            "provider", "session_id", "driver_number", name="uq_session_driver_external"
        ),
        UniqueConstraint(
            "provider", "session_id", "driver_id", name="uq_session_driver_domain"
        ),
        CheckConstraint("driver_number > 0", name="positive_number"),
    )

    provider: Mapped[str] = mapped_column(String(50))
    session_id: Mapped[UUID] = mapped_column(ForeignKey("sessions.id"), index=True)
    driver_id: Mapped[UUID] = mapped_column(ForeignKey("drivers.id"), index=True)
    driver_number: Mapped[int]


class SourceFields:
    session_id: Mapped[UUID] = mapped_column(ForeignKey("sessions.id"), index=True)
    provider: Mapped[str] = mapped_column(String(50))
    source_key: Mapped[str] = mapped_column(String(200))
    source_record_id: Mapped[UUID] = mapped_column(
        ForeignKey("telemetry_source_records.id")
    )
    # Import ordering metadata, not upstream telemetry or immutable revision time.
    source_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DriverFields:
    driver_id: Mapped[UUID] = mapped_column(ForeignKey("drivers.id"), index=True)


def source_identity(table: str):
    return UniqueConstraint(
        "provider", "session_id", "source_key", name=f"uq_{table}_source"
    )


class Lap(SourceFields, DriverFields, Entity, Base):
    __tablename__ = "laps"
    __table_args__ = (
        source_identity("laps"),
        UniqueConstraint(
            "provider",
            "session_id",
            "driver_id",
            "lap_number",
            name="uq_laps_driver_number",
        ),
        UniqueConstraint(
            "id", "session_id", "driver_id", "provider", name="uq_laps_sample_scope"
        ),
        CheckConstraint("lap_number > 0", name="positive_lap"),
        CheckConstraint(
            "duration_seconds >= 0 AND sector_1_seconds >= 0 AND "
            "sector_2_seconds >= 0 AND sector_3_seconds >= 0",
            name="nonnegative_durations",
        ),
    )

    lap_number: Mapped[int]
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    sector_1_seconds: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    sector_2_seconds: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    sector_3_seconds: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    is_pit_out_lap: Mapped[bool | None]
    start_time_is_approximate: Mapped[bool]


class TelemetrySample(SourceFields, DriverFields, Entity, Base):
    __tablename__ = "telemetry_samples"
    __table_args__ = (
        source_identity("telemetry_samples"),
        UniqueConstraint(
            "provider",
            "session_id",
            "driver_id",
            "timestamp",
            name="uq_telemetry_driver_time",
        ),
        ForeignKeyConstraint(
            ["lap_id", "session_id", "driver_id", "provider"],
            ["laps.id", "laps.session_id", "laps.driver_id", "laps.provider"],
            name="fk_telemetry_lap_scope",
        ),
        CheckConstraint("speed_kph >= 0 AND rpm >= 0", name="nonnegative_channels"),
        CheckConstraint("throttle_percent BETWEEN 0 AND 100", name="throttle_range"),
        CheckConstraint("gear BETWEEN 0 AND 8", name="gear_range"),
        CheckConstraint("drs_state >= 0", name="nonnegative_drs"),
    )

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    lap_id: Mapped[UUID | None] = mapped_column(index=True)
    speed_kph: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    throttle_percent: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    brake_applied: Mapped[bool | None]
    gear: Mapped[int | None]
    rpm: Mapped[int | None]
    drs_state: Mapped[int | None]


class Stint(SourceFields, DriverFields, Entity, Base):
    __tablename__ = "stints"
    __table_args__ = (
        source_identity("stints"),
        UniqueConstraint(
            "provider",
            "session_id",
            "driver_id",
            "stint_number",
            name="uq_stints_driver_number",
        ),
        CheckConstraint("stint_number > 0 AND lap_start > 0", name="positive_numbers"),
        CheckConstraint("lap_end >= lap_start", name="lap_order"),
        CheckConstraint("tyre_age_at_start >= 0", name="nonnegative_age"),
    )

    stint_number: Mapped[int]
    lap_start: Mapped[int | None]
    lap_end: Mapped[int | None]
    compound: Mapped[str | None] = mapped_column(String(30))
    tyre_age_at_start: Mapped[int | None]


class PitStop(SourceFields, DriverFields, Entity, Base):
    __tablename__ = "pit_stops"
    __table_args__ = (
        source_identity("pit_stops"),
        UniqueConstraint(
            "provider",
            "session_id",
            "driver_id",
            "timestamp",
            name="uq_pits_driver_time",
        ),
        CheckConstraint("lap_number > 0", name="positive_lap"),
        CheckConstraint(
            "lane_duration_seconds >= 0 AND stop_duration_seconds >= 0",
            name="nonnegative_durations",
        ),
    )

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    lap_number: Mapped[int | None]
    lane_duration_seconds: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    stop_duration_seconds: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))


class PositionSample(SourceFields, DriverFields, Entity, Base):
    __tablename__ = "position_samples"
    __table_args__ = (
        source_identity("position_samples"),
        UniqueConstraint(
            "provider",
            "session_id",
            "driver_id",
            "timestamp",
            name="uq_positions_driver_time",
        ),
        CheckConstraint("position > 0", name="positive_position"),
    )

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    position: Mapped[int | None]


class IntervalSample(SourceFields, DriverFields, Entity, Base):
    __tablename__ = "interval_samples"
    __table_args__ = (
        source_identity("interval_samples"),
        UniqueConstraint(
            "provider",
            "session_id",
            "driver_id",
            "timestamp",
            name="uq_intervals_driver_time",
        ),
        CheckConstraint(
            "gap_to_leader_seconds IS NULL OR gap_to_leader_laps IS NULL",
            name="exclusive_gap_units",
        ),
        CheckConstraint(
            "interval_seconds IS NULL OR interval_laps IS NULL",
            name="exclusive_interval_units",
        ),
        CheckConstraint(
            "gap_to_leader_laps >= 0 AND interval_laps >= 0",
            name="nonnegative_lap_gaps",
        ),
    )

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    gap_to_leader_seconds: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    gap_to_leader_laps: Mapped[int | None]
    interval_seconds: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    interval_laps: Mapped[int | None]


class RaceControlMessage(SourceFields, Entity, Base):
    __tablename__ = "race_control_messages"
    __table_args__ = (source_identity("race_control_messages"),)

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    driver_id: Mapped[UUID | None] = mapped_column(ForeignKey("drivers.id"), index=True)
    category: Mapped[str | None] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(Text)
    flag: Mapped[str | None] = mapped_column(String(100))
    scope: Mapped[str | None] = mapped_column(String(100))
    lap_number: Mapped[int | None]
    sector: Mapped[int | None]
    qualifying_phase: Mapped[int | None]


class WeatherSample(SourceFields, Entity, Base):
    __tablename__ = "weather_samples"
    __table_args__ = (
        source_identity("weather_samples"),
        UniqueConstraint("provider", "session_id", "timestamp", name="uq_weather_time"),
        CheckConstraint("humidity_percent BETWEEN 0 AND 100", name="humidity_range"),
        CheckConstraint("wind_direction_degrees BETWEEN 0 AND 359", name="wind_range"),
        CheckConstraint(
            "pressure_mbar >= 0 AND wind_speed_mps >= 0", name="nonnegative_channels"
        ),
    )

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    air_temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    track_temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    humidity_percent: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    pressure_mbar: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    rainfall: Mapped[bool | None]
    wind_direction_degrees: Mapped[int | None]
    wind_speed_mps: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))

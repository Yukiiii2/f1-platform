"""Bounded application replay contract; order is not a coordinate."""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field

from app.schemas.domain import DriverRead, Schema, SessionRead, TeamRead


class ReplayPosition(Schema):
    id: UUID
    timestamp: AwareDatetime
    elapsed_seconds: float = Field(ge=0)
    position: int = Field(gt=0)


class ReplayInterval(Schema):
    timestamp: AwareDatetime
    elapsed_seconds: float = Field(ge=0)
    gap_to_leader_seconds: Decimal | None = None
    gap_to_leader_laps: int | None = None


class ReplayLap(Schema):
    lap_number: int
    starts_at: AwareDatetime
    start_seconds: float
    end_seconds: float | None = None
    approximate: bool


class ReplayPit(Schema):
    timestamp: AwareDatetime
    elapsed_seconds: float
    lane_duration_seconds: Decimal | None = None
    lap_number: int | None = None


class ReplayControl(Schema):
    id: UUID
    timestamp: AwareDatetime
    elapsed_seconds: float
    message: str = Field(max_length=500)
    category: str | None = None
    flag: str | None = None
    scope: str | None = None
    driver_id: UUID | None = None
    lap_number: int | None = None


class ReplayDriver(Schema):
    driver: DriverRead
    team: TeamRead | None = None
    source_sample_count: int
    positions: list[ReplayPosition] = Field(max_length=600)
    intervals: list[ReplayInterval] = Field(default_factory=list, max_length=600)
    laps: list[ReplayLap] = Field(default_factory=list, max_length=200)
    pits: list[ReplayPit] = Field(default_factory=list, max_length=50)
    inactive_state: None = None


class ReplayQuality(Schema):
    method: Literal["recorded-order-v1"] = "recorded-order-v1"
    interpolation: Literal["previous_sample_hold"] = "previous_sample_hold"
    max_hold_seconds: int = 30
    coordinates_available: Literal[False] = False
    gaps_present: bool = False
    downsampled: bool = False
    truncated_context: bool = False
    omitted_driver_count: int = 0
    sampling_seconds: float = 0
    notes: list[str] = Field(default_factory=list)


class SessionReplay(Schema):
    session: SessionRead
    event_id: UUID
    event_name: str
    season: int
    capability: Literal["available", "partial", "unavailable"] = "unavailable"
    mode: Literal["timing_order"] = "timing_order"
    provisional: bool
    provider: str | None = None
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    duration_seconds: float = 0
    drivers: list[ReplayDriver] = Field(default_factory=list, max_length=32)
    race_control: list[ReplayControl] = Field(default_factory=list, max_length=200)
    quality: ReplayQuality = Field(default_factory=ReplayQuality)

"""Completed-race strategy summaries over normalized session records."""

from typing import Literal
from uuid import UUID

from app.schemas.domain import Schema
from app.schemas.telemetry import Number, PitStopRead, RaceControlMessageRead, StintRead


class PaceRead(Schema):
    recorded_laps: int
    included_laps: int
    excluded_laps: int
    average_seconds: Number | None
    best_seconds: Number | None
    unavailable_reason: (
        Literal["stint_context", "pit_lap_context", "no_eligible_laps"] | None
    )
    classification: Literal["derived"] = "derived"
    policy_version: Literal["observed-non-pit-v1"] = "observed-non-pit-v1"


class StrategyStintRead(Schema):
    source: StintRead
    context_status: Literal["available", "ambiguous", "unavailable"]
    age_completed_lap: int | None
    completed_laps_on_stint: int | None
    total_tyre_age: int | None
    age_classification: Literal["derived"] = "derived"
    age_formula_version: Literal["completed-laps-v1"] = "completed-laps-v1"
    pace: PaceRead


class DriverStrategyRead(Schema):
    driver_id: UUID
    provider: str
    recorded_lap_count: int
    stints: list[StrategyStintRead]
    pits: list[PitStopRead]


class StrategyRead(Schema):
    session_id: UUID
    lap_axis_end: int | None
    drivers: list[DriverStrategyRead]
    race_control: list[RaceControlMessageRead]

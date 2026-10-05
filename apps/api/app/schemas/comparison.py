from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.domain import Schema
from app.schemas.telemetry import LapCreate

Alignment = Literal["normalized_distance", "elapsed_time"]
Association = Literal["confirmed", "approximate_window", "unavailable"]
Value = Annotated[Decimal, Field(allow_inf_nan=False)]


class CompareRequest(Schema):
    lap_a_id: UUID
    lap_b_id: UUID
    sample_count: int = Field(default=201, ge=2, le=2001)
    alignment: Alignment = "normalized_distance"
    allow_approximate: bool = False

    @model_validator(mode="after")
    def distinct_laps(self) -> Self:
        if self.lap_a_id == self.lap_b_id:
            raise ValueError("Choose two different laps")
        return self


class LapSummary(LapCreate):
    id: UUID


class TyreContext(Schema):
    status: Literal["available", "unavailable", "ambiguous"] = "unavailable"
    stint_id: UUID | None = None
    compound: str | None = None
    lap_start: int | None = None
    lap_end: int | None = None
    tyre_age_at_start: int | None = None
    completed_laps_before: int | None = None
    completed_laps_after: int | None = None
    total_age_before: int | None = None
    total_age_after: int | None = None
    age_classification: Literal["derived"] = "derived"
    formula_version: Literal["completed-laps-v1"] = "completed-laps-v1"


class ComparedLap(Schema):
    lap: LapSummary
    tyres: TyreContext


class SectorDeltas(Schema):
    sector_1: Value | None = None
    sector_2: Value | None = None
    sector_3: Value | None = None


class Channels(Schema):
    speed_kph: Value | None = None
    throttle_percent: Value | None = None
    rpm: Value | None = None
    brake_applied: bool | None = None
    gear: int | None = None
    drs_state: int | None = None


class TracePoint(Schema):
    coordinate: Value
    elapsed_seconds_a: Value | None
    elapsed_seconds_b: Value | None
    delta_ms: Value | None
    channels_a: Channels
    channels_b: Channels


class AlignedTrace(Schema):
    requested_alignment: Alignment
    alignment: Alignment | None = None
    axis: Literal["fraction_of_integrated_distance", "elapsed_seconds"] | None = None
    availability: Literal["available", "partial", "unavailable"] = "unavailable"
    classification: Literal["derived", "estimate"] = "derived"
    association_a: Association
    association_b: Association
    sample_count_a: int
    sample_count_b: int
    sample_resolution: Value | None = None
    max_interpolation_gap_seconds: Value = Decimal("1")
    continuous_interpolation: Literal["linear"] = "linear"
    discrete_interpolation: Literal["previous_sample"] = "previous_sample"
    distance_method: Literal["trapezoidal_speed_integration"] | None = None
    distance_a_m: Value | None = None
    distance_b_m: Value | None = None
    distance_is_track_position: Literal[False] = False
    delta_available: bool = False
    warnings: list[str] = Field(default_factory=list)
    points: list[TracePoint] = Field(default_factory=list)


class CompareResponse(Schema):
    lap_a: ComparedLap
    lap_b: ComparedLap
    lap_delta_ms: Value | None
    sector_delta_ms: SectorDeltas
    delta_classification: Literal["derived"] = "derived"
    delta_sign: Literal["a_minus_b_positive_a_slower"] = "a_minus_b_positive_a_slower"
    formula_version: Literal["lap-comparison-v1"] = "lap-comparison-v1"
    trace: AlignedTrace

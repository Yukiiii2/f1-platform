from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from app.schemas.domain import ReadFields, Schema

Number = Annotated[Decimal, Field(max_digits=14, decimal_places=6, allow_inf_nan=False)]
Nonnegative = Annotated[Number, Field(ge=0)]
PositiveInt = Annotated[int, Field(gt=0)]
Text = Annotated[str, Field(max_length=100)]


class SourceFields(Schema):
    session_id: UUID
    provider: Annotated[str, Field(min_length=1, max_length=50)]


class DriverFields(SourceFields):
    driver_id: UUID


class LapCreate(DriverFields):
    lap_number: PositiveInt
    starts_at: AwareDatetime | None = None
    duration_seconds: Nonnegative | None = None
    sector_1_seconds: Nonnegative | None = None
    sector_2_seconds: Nonnegative | None = None
    sector_3_seconds: Nonnegative | None = None
    is_pit_out_lap: bool | None = None
    start_time_is_approximate: bool


class LapRead(LapCreate, ReadFields):
    pass


class TelemetrySampleCreate(DriverFields):
    timestamp: AwareDatetime
    lap_id: UUID | None = None
    speed_kph: Nonnegative | None = None
    throttle_percent: Annotated[Nonnegative, Field(le=100)] | None = None
    brake_applied: bool | None = None
    gear: Annotated[int, Field(ge=0, le=8)] | None = None
    rpm: Annotated[int, Field(ge=0)] | None = None
    drs_state: Annotated[int, Field(ge=0)] | None = None


class TelemetrySampleRead(TelemetrySampleCreate, ReadFields):
    pass


class StintCreate(DriverFields):
    stint_number: PositiveInt
    lap_start: PositiveInt | None = None
    lap_end: PositiveInt | None = None
    compound: Annotated[str, Field(max_length=30)] | None = None
    tyre_age_at_start: Annotated[int, Field(ge=0)] | None = None

    @model_validator(mode="after")
    def ordered_laps(self) -> Self:
        if self.lap_start is not None and self.lap_end is not None:
            if self.lap_end < self.lap_start:
                raise ValueError("Stint lap boundaries are reversed")
        return self


class StintRead(StintCreate, ReadFields):
    pass


class PitStopCreate(DriverFields):
    timestamp: AwareDatetime
    lap_number: PositiveInt | None = None
    lane_duration_seconds: Nonnegative | None = None
    stop_duration_seconds: Nonnegative | None = None


class PitStopRead(PitStopCreate, ReadFields):
    pass


class PositionSampleCreate(DriverFields):
    timestamp: AwareDatetime
    position: PositiveInt | None = None


class PositionSampleRead(PositionSampleCreate, ReadFields):
    pass


class IntervalSampleCreate(DriverFields):
    timestamp: AwareDatetime
    gap_to_leader_seconds: Number | None = None
    gap_to_leader_laps: Annotated[int, Field(ge=0)] | None = None
    interval_seconds: Number | None = None
    interval_laps: Annotated[int, Field(ge=0)] | None = None

    @model_validator(mode="after")
    def exclusive_units(self) -> Self:
        for name in ("gap_to_leader", "interval"):
            if getattr(self, name + "_seconds") is not None:
                if getattr(self, name + "_laps") is not None:
                    raise ValueError("A gap cannot have both time and lap units")
        return self


class IntervalSampleRead(IntervalSampleCreate, ReadFields):
    pass


class RaceControlMessageCreate(SourceFields):
    timestamp: AwareDatetime
    driver_id: UUID | None = None
    category: Text | None = None
    message: Annotated[str, Field(min_length=1)]
    flag: Text | None = None
    scope: Text | None = None
    lap_number: PositiveInt | None = None
    sector: PositiveInt | None = None
    qualifying_phase: Annotated[int, Field(ge=1, le=3)] | None = None


class RaceControlMessageRead(RaceControlMessageCreate, ReadFields):
    pass


class WeatherSampleCreate(SourceFields):
    timestamp: AwareDatetime
    air_temperature_c: Number | None = None
    track_temperature_c: Number | None = None
    humidity_percent: Annotated[Nonnegative, Field(le=100)] | None = None
    pressure_mbar: Nonnegative | None = None
    rainfall: bool | None = None
    wind_direction_degrees: Annotated[int, Field(ge=0, le=359)] | None = None
    wind_speed_mps: Nonnegative | None = None


class WeatherSampleRead(WeatherSampleCreate, ReadFields):
    pass


class TyreAgeRead(Schema):
    stint_id: UUID
    completed_lap: int
    tyre_age_at_start: int | None
    completed_laps_on_stint: int
    total_tyre_age: int | None
    classification: str = "derived"
    formula_version: str = "completed-laps-v1"

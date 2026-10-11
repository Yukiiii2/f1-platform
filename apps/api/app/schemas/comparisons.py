"""Versioned, allow-listed presets for existing comparison pages."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.domain import Schema

ComparisonType = Literal["telemetry_laps", "strategy_tyres"]


class Context(Schema):
    version: Literal[1] = 1
    season: int = Field(ge=1950, le=9999)
    event_id: UUID
    session_id: UUID
    driver_a_id: UUID
    driver_b_id: UUID


class TelemetryConfiguration(Context):
    lap_a_id: UUID
    lap_b_id: UUID
    alignment: Literal["normalized_distance", "elapsed_time"] = "normalized_distance"
    allow_approximate: bool = False

    @model_validator(mode="after")
    def distinct_laps(self):
        if self.lap_a_id == self.lap_b_id:
            raise ValueError("Choose two distinct recorded laps")
        return self


class StrategyConfiguration(Context):
    provider_a: str = Field(min_length=1, max_length=50, pattern=r"^[a-z0-9_-]+$")
    provider_b: str = Field(min_length=1, max_length=50, pattern=r"^[a-z0-9_-]+$")

    @model_validator(mode="after")
    def distinct_records(self):
        if (self.driver_a_id, self.provider_a) == (self.driver_b_id, self.provider_b):
            raise ValueError("Choose two distinct recorded strategies")
        return self


Configuration = TelemetryConfiguration | StrategyConfiguration


class UnavailableConfiguration(Schema):
    """Safe identity snapshot when a stored version/settings can no longer reopen."""

    version: int | None
    season: int
    event_id: UUID | None
    session_id: UUID | None
    driver_a_id: UUID | None
    driver_b_id: UUID | None
    lap_a_id: UUID | None
    lap_b_id: UUID | None


class ComparisonCreate(Schema):
    title: str = Field(min_length=1, max_length=120)
    comparison_type: ComparisonType
    configuration: Configuration

    @model_validator(mode="after")
    def matching_type(self):
        expected = (
            TelemetryConfiguration
            if self.comparison_type == "telemetry_laps"
            else StrategyConfiguration
        )
        if not isinstance(self.configuration, expected):
            raise ValueError("Configuration does not match comparison type")
        return self


class ComparisonUpdate(Schema):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    configuration: Configuration | None = None

    @model_validator(mode="after")
    def nonempty(self):
        if not self.model_fields_set or any(
            getattr(self, key) is None for key in self.model_fields_set
        ):
            raise ValueError("Supply a title or configuration, not null")
        return self


class ComparisonRead(Schema):
    id: UUID
    title: str
    comparison_type: ComparisonType
    source_route: Literal["/telemetry", "/strategy"]
    configuration: Configuration | UnavailableConfiguration
    created_at: datetime
    updated_at: datetime
    event_name: str | None
    session_name: str | None
    driver_a_name: str | None
    driver_b_name: str | None
    lap_a_number: int | None
    lap_b_number: int | None
    availability: Literal["available", "partial", "unavailable"]
    notices: list[str]
    open_url: str | None

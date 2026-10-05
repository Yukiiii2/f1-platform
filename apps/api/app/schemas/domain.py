from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.domain.enums import SessionStatus, SessionType

Name = Annotated[str, Field(min_length=1, max_length=200)]
ShortName = Annotated[str, Field(min_length=1, max_length=100)]
Points = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=3)]


class Schema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True, extra="forbid", str_strip_whitespace=True
    )


class ReadFields(Schema):
    id: UUID
    created_at: AwareDatetime
    updated_at: AwareDatetime


class TimeWindow(Schema):
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def ordered_times(self) -> Self:
        if self.starts_at and self.ends_at and self.ends_at < self.starts_at:
            raise ValueError("ends_at must be on or after starts_at")
        return self


class SeasonCreate(Schema):
    year: int = Field(ge=1950)


class SeasonRead(SeasonCreate, ReadFields):
    pass


class CircuitCreate(Schema):
    name: Name
    country: ShortName
    locality: ShortName | None = None
    timezone: Annotated[str, Field(min_length=1, max_length=64)] | None = None

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError) as error:
                raise ValueError("timezone must be an IANA timezone name") from error
        return value


class CircuitRead(CircuitCreate, ReadFields):
    pass


class EventCreate(TimeWindow):
    season_id: UUID
    circuit_id: UUID
    round: int = Field(gt=0)
    name: Name


class EventRead(EventCreate, ReadFields):
    pass


class SessionCreate(TimeWindow):
    event_id: UUID
    type: SessionType
    status: SessionStatus = SessionStatus.UNKNOWN


class SessionRead(SessionCreate, ReadFields):
    pass


class DriverCreate(Schema):
    given_name: ShortName
    family_name: ShortName
    code: (
        Annotated[str, Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")] | None
    ) = None
    permanent_number: Annotated[int, Field(ge=1, le=99)] | None = None
    nationality: ShortName | None = None


class DriverRead(DriverCreate, ReadFields):
    pass


class TeamCreate(Schema):
    name: Name
    nationality: ShortName | None = None


class TeamRead(TeamCreate, ReadFields):
    pass


class ResultCreate(Schema):
    session_id: UUID
    driver_id: UUID
    team_id: UUID
    position: Annotated[int, Field(gt=0)] | None = None
    grid_position: Annotated[int, Field(ge=0)] | None = None
    points: Points | None = None
    completed_laps: Annotated[int, Field(ge=0)] | None = None
    status: ShortName | None = None
    total_time_ms: Annotated[int, Field(gt=0)] | None = None
    gap_ms: Annotated[int, Field(ge=0)] | None = None


class ResultRead(ResultCreate, ReadFields):
    pass


class StandingFields(Schema):
    season_id: UUID
    event_id: UUID
    position: int = Field(gt=0)
    points: Points
    wins: int = Field(ge=0)


class DriverStandingCreate(StandingFields):
    driver_id: UUID


class DriverStandingRead(DriverStandingCreate, ReadFields):
    pass


class ConstructorStandingCreate(StandingFields):
    team_id: UUID


class ConstructorStandingRead(ConstructorStandingCreate, ReadFields):
    pass

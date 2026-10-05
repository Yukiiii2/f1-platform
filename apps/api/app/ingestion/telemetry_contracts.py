from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

from app.domain.enums import SessionType

TelemetryKind = Literal[
    "lap",
    "telemetry",
    "stint",
    "pit",
    "position",
    "interval",
    "race_control",
    "weather",
]


@dataclass(frozen=True)
class TelemetryRecord:
    kind: TelemetryKind
    source_key: str
    attributes: dict[str, Any]
    source_payload: dict[str, Any]
    driver_number: int | None = None


@dataclass(frozen=True)
class TelemetryBundle:
    records: list[TelemetryRecord]
    fetched_at: datetime
    year: int
    session_type: SessionType
    starts_at: datetime
    ends_at: datetime
    country: str
    driver_codes: dict[int, str | None]
    source_updated_at: datetime | None = None


class TelemetryProvider(Protocol):
    name: str

    def fetch_session(
        self, source_session: int, drivers: list[int]
    ) -> TelemetryBundle: ...

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

EntityKind = Literal[
    "season",
    "circuit",
    "event",
    "session",
    "driver",
    "team",
    "result",
    "driver_standing",
    "constructor_standing",
]


@dataclass(frozen=True)
class NormalizedRecord:
    kind: EntityKind
    external_id: str
    attributes: dict[str, Any]
    # Foreign-key field -> external identity within the same provider.
    references: dict[str, tuple[EntityKind, str]]


@dataclass(frozen=True)
class ImportBundle:
    records: list[NormalizedRecord]
    fetched_at: datetime
    source_updated_at: datetime | None = None
    raw_payload: dict | None = None

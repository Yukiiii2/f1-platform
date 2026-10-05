from typing import Protocol

from app.ingestion.contracts import ImportBundle


class ProviderError(Exception):
    """Safe, actionable upstream failure without request credentials or payloads."""


class F1Provider(Protocol):
    name: str

    def fetch(self, year: int, round_number: int | None = None) -> ImportBundle: ...

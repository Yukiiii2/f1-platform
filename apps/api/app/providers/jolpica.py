import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from app.ingestion.contracts import ImportBundle
from app.providers.base import ProviderError
from app.providers.jolpica_normalization import normalize

logger = logging.getLogger(__name__)


class JolpicaProvider:
    name = "jolpica"
    base_url = "https://api.jolpi.ca/ergast/f1/"

    def __init__(
        self,
        client: httpx.Client | None = None,
        request_interval: float = 0.35,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.client = client or httpx.Client(timeout=15)
        self.owns_client = client is None
        self.request_interval = request_interval
        self.sleep = sleep
        self.last_request = 0.0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self.owns_client:
            self.client.close()

    def _request(self, path: str, offset: int) -> dict:
        for attempt in range(3):
            self.sleep(
                max(0, self.request_interval - (time.monotonic() - self.last_request))
            )
            self.last_request = time.monotonic()
            try:
                response = self.client.get(
                    self.base_url + path,
                    params={"limit": 100, "offset": offset},
                    headers={"User-Agent": "F1IntelligencePlatform/0.2.0"},
                )
            except httpx.RequestError:
                logger.warning(
                    "Jolpica transport failure: endpoint=%s attempt=%d",
                    path,
                    attempt + 1,
                )
                if attempt == 2:
                    raise ProviderError(
                        "Jolpica request failed after 3 attempts"
                    ) from None
                self.sleep(2**attempt)
                continue
            if response.status_code == 429 or response.status_code >= 500:
                logger.warning(
                    "Jolpica response failure: endpoint=%s status=%d attempt=%d",
                    path,
                    response.status_code,
                    attempt + 1,
                )
                delay = float(2**attempt)
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        delay = max(delay, float(retry_after))
                    except ValueError:
                        try:
                            until = parsedate_to_datetime(retry_after)
                            delay = max(
                                delay,
                                (until - datetime.now(timezone.utc)).total_seconds(),
                            )
                        except (ValueError, TypeError):
                            pass
                if attempt == 2 or delay > 60:
                    raise ProviderError(
                        f"Jolpica HTTP {response.status_code}; retry import later"
                    )
                self.sleep(delay)
                continue
            if response.status_code != 200:
                raise ProviderError(
                    f"Jolpica HTTP {response.status_code}; request not retried"
                )
            try:
                return response.json()["MRData"]
            except (ValueError, KeyError, TypeError):
                raise ProviderError(
                    "Jolpica returned an invalid JSON envelope"
                ) from None
        raise ProviderError("Jolpica retry limit exceeded")

    def _pages(
        self, path: str, table: str, key: str, nested: str | None = None
    ) -> list[dict]:
        output = []
        offset = 0
        expected_total = None
        while True:
            body = self._request(path, offset)
            try:
                total, limit = int(body["total"]), int(body["limit"])
                rows = body[table][key]
                count = sum(len(row[nested]) for row in rows) if nested else len(rows)
                if not isinstance(rows, list) or int(body["offset"]) != offset:
                    raise ValueError
                if total < 0 or limit <= 0 or count > limit or offset + count > total:
                    raise ValueError
            except (ValueError, TypeError, KeyError):
                raise ProviderError(
                    "Jolpica returned invalid pagination data"
                ) from None
            if expected_total is not None and total != expected_total:
                raise ProviderError(
                    "Jolpica pagination changed during import; retry later"
                )
            expected_total = total
            output.extend(rows)
            offset += count
            if offset == total:
                return output
            if count == 0:
                raise ProviderError("Jolpica returned an incomplete page")

    def fetch(self, year: int, round_number: int | None = None) -> ImportBundle:
        if year < 1950 or (round_number is not None and round_number < 1):
            raise ValueError("Invalid season or round")
        observed = datetime.now(timezone.utc)
        prefix = f"{year}/" + (f"{round_number}/" if round_number else "")
        data = {}
        for endpoint, table, key, nested in [
            ("races", "RaceTable", "Races", None),
            ("drivers", "DriverTable", "Drivers", None),
            ("constructors", "ConstructorTable", "Constructors", None),
            ("results", "RaceTable", "Races", "Results"),
            ("qualifying", "RaceTable", "Races", "QualifyingResults"),
            ("sprint", "RaceTable", "Races", "SprintResults"),
            ("driverstandings", "StandingsTable", "StandingsLists", "DriverStandings"),
            (
                "constructorstandings",
                "StandingsTable",
                "StandingsLists",
                "ConstructorStandings",
            ),
        ]:
            data[endpoint] = self._pages(
                prefix + endpoint + ".json", table, key, nested
            )
        try:
            return normalize(data, year, round_number, observed_at=observed)
        except (ValueError, TypeError, KeyError) as error:
            raise ProviderError(
                "Jolpica core data is incomplete or inconsistent"
            ) from error

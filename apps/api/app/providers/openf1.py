import logging
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx

from app.domain.enums import SessionType
from app.ingestion.telemetry_contracts import SessionCompletion
from app.providers.base import ProviderError
from app.providers.openf1_normalization import (
    KINDS,
    SESSION_TYPES,
    normalize,
    timestamp,
)

logger = logging.getLogger(__name__)


class OpenF1Provider:
    """Explicit historical imports. No authentication, polling, or live access."""

    name = "openf1"
    base_url = "https://api.openf1.org/v1/"

    def __init__(
        self,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.client = client or httpx.Client(timeout=60)
        self.owns_client = client is None
        self.sleep = sleep
        self.last_request = 0.0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self.owns_client:
            self.client.close()

    def _request(self, endpoint, params, allow_empty=False):
        for attempt in range(3):
            # Free tier: 3/s and 30/min. 2.1 seconds also leaves minute-window headroom.
            self.sleep(max(0, 2.1 - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                response = self.client.get(
                    self.base_url + endpoint,
                    params=params,
                    headers={"User-Agent": "F1IntelligencePlatform/0.4.0"},
                )
            except httpx.RequestError:
                logger.warning(
                    "OpenF1 transport failure: endpoint=%s attempt=%d",
                    endpoint,
                    attempt + 1,
                )
                if attempt == 2:
                    raise ProviderError(
                        "OpenF1 transport failed after 3 attempts"
                    ) from None
                self.sleep(2**attempt)
                continue
            if response.status_code == 429 or response.status_code >= 500:
                logger.warning(
                    "OpenF1 response failure: endpoint=%s status=%d attempt=%d",
                    endpoint,
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
                            delay = max(
                                delay,
                                (
                                    parsedate_to_datetime(retry_after)
                                    - datetime.now(timezone.utc)
                                ).total_seconds(),
                            )
                        except (ValueError, TypeError):
                            pass
                if attempt == 2 or delay > 60:
                    raise ProviderError(
                        f"OpenF1 HTTP {response.status_code}; retry import later"
                    )
                self.sleep(delay)
                continue
            try:
                body = response.json()
            except ValueError:
                raise ProviderError("OpenF1 returned invalid JSON") from None
            if (
                allow_empty
                and response.status_code == 404
                and body == {"detail": "No results found."}
            ):
                return []
            if response.status_code != 200:
                raise ProviderError(
                    f"OpenF1 HTTP {response.status_code}; request not retried"
                )
            if not isinstance(body, list) or any(
                not isinstance(row, dict) for row in body
            ):
                raise ProviderError("OpenF1 returned an invalid collection")
            return body
        raise ProviderError("OpenF1 retry limit exceeded")

    def fetch_session(self, source_session: int, drivers: list[int]):
        if source_session < 1 or not drivers or any(number < 1 for number in drivers):
            raise ValueError(
                "Explicit source session and positive driver numbers are required"
            )
        params = {"session_key": source_session}
        data = {"sessions": self._request("sessions", params)}
        try:
            metadata = data["sessions"]
            if len(metadata) != 1 or metadata[0]["session_key"] != source_session:
                raise ValueError
            end = timestamp(metadata[0]["date_end"])
            if end + timedelta(minutes=30) > datetime.now(timezone.utc):
                raise ProviderError(
                    "Historical import requires a session ended over 30 minutes ago"
                )
            data["drivers"] = self._request("drivers", params)
            for endpoint in KINDS:
                data[endpoint] = []
                if endpoint in {"race_control", "weather"}:
                    data[endpoint] = self._request(endpoint, params, allow_empty=True)
                else:
                    for number in sorted(set(drivers)):
                        data[endpoint].extend(
                            self._request(
                                endpoint,
                                {**params, "driver_number": number},
                                allow_empty=True,
                            )
                        )
            return normalize(data, source_session, drivers, datetime.now(timezone.utc))
        except (ValueError, TypeError, KeyError) as error:
            raise ProviderError("OpenF1 data is incomplete or inconsistent") from error

    def inspect_session(self, source_session: int, now: datetime) -> SessionCompletion:
        """Low-frequency historical completion check; date_end alone is not proof."""
        if source_session < 1 or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Positive source session and aware clock are required")
        try:
            metadata = self._request("sessions", {"session_key": source_session})
            if len(metadata) != 1 or metadata[0]["session_key"] != source_session:
                raise ValueError("Mismatched source session")
            row = metadata[0]
            cancelled = row.get("is_cancelled", False)
            if not isinstance(cancelled, bool):
                raise ValueError("Invalid source cancellation flag")
            start = (
                timestamp(row["date_start"])
                if row.get("date_start") is not None
                else None
            )
            end = (
                timestamp(row["date_end"]) if row.get("date_end") is not None else None
            )
            if not cancelled and (start is None or end is None):
                raise ValueError("Source session window unavailable")
            if start and end and end < start:
                raise ValueError("Invalid source session window")
            context = dict(
                year=int(row["year"]),
                session_type=SESSION_TYPES[row["session_name"]],
                starts_at=start,
                ends_at=end,
                country=row["country_name"],
                settled=bool(end and end + timedelta(minutes=30) <= now),
            )
            if cancelled:
                return SessionCompletion(**context, cancelled=True)
            if not context["settled"]:
                return SessionCompletion(**context)
            signals = self._request(
                "race_control", {"session_key": source_session}, allow_empty=True
            )
            eligible = []
            statuses = []
            qualifying = context["session_type"] in {
                SessionType.QUALIFYING,
                SessionType.SPRINT_QUALIFYING,
            }
            for signal in signals:
                if signal["session_key"] != source_session:
                    raise ValueError("Mismatched race-control session")
                observed = timestamp(signal["date"])
                if observed < start or observed > now:
                    continue
                message = signal.get("message", "").strip().upper()
                if signal.get("driver_number") is not None:
                    continue
                if signal.get("category") == "SessionStatus":
                    statuses.append((observed, message))
                final_phase = not qualifying or signal.get("qualifying_phase") == 3
                if (
                    signal.get("category") == "SessionStatus"
                    and message == "SESSION ENDED"
                    and final_phase
                ):
                    eligible.append((observed, "session_ended"))
                if (
                    signal.get("flag") == "CHEQUERED"
                    and signal.get("scope") == "Track"
                    and observed >= end - timedelta(minutes=15)
                    and final_phase
                ):
                    eligible.append((observed, "chequered"))
            cancelled = bool(statuses and max(statuses)[1] == "SESSION CANCELLED")
            active_since = max(
                (
                    observed
                    for observed, message in statuses
                    if message
                    in {
                        "SESSION STARTED",
                        "SESSION RESUMED",
                        "SESSION RESTARTED",
                        "SESSION STOPPED",
                        "SESSION ABORTED",
                    }
                ),
                default=start,
            )
            eligible = [proof for proof in eligible if proof[0] >= active_since]
            proof = max(eligible) if eligible and not cancelled else None
            return SessionCompletion(
                **context,
                completed=proof is not None,
                cancelled=cancelled,
                evidence_kind=proof[1] if proof else None,
                observed_at=proof[0] if proof else None,
            )
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            raise ProviderError("OpenF1 completion metadata is invalid") from error

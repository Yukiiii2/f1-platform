import logging
import time
from collections.abc import Callable
from dataclasses import replace
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
    """Historical imports and opt-in authenticated incremental observations."""

    name = "openf1"
    base_url = "https://api.openf1.org/v1/"

    def __init__(
        self,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        *,
        username: str | None = None,
        password: str | None = None,
    ):
        self.client = client or httpx.Client(timeout=60)
        self.owns_client = client is None
        self.sleep = sleep
        self.last_request = 0.0
        self.username, self.password = username, password
        self._token = None
        self._token_expires = 0.0
        self._live_observation = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self.owns_client:
            self.client.close()

    def _authorization(self):
        if not self.username or not self.password:
            raise ProviderError("OpenF1 live access is not configured")
        if self._token and time.monotonic() < self._token_expires:
            return {"Authorization": f"Bearer {self._token}"}
        try:
            response = self.client.post(
                "https://api.openf1.org/token",
                data={"username": self.username, "password": self.password},
            )
            if response.status_code != 200:
                raise ProviderError(
                    f"OpenF1 authentication HTTP {response.status_code}"
                )
            body = response.json()
            token, lifetime = body["access_token"], int(body["expires_in"])
            if not isinstance(token, str) or not token or lifetime <= 60:
                raise ValueError
        except (httpx.RequestError, ValueError, KeyError, TypeError):
            raise ProviderError("OpenF1 authentication unavailable") from None
        self._token, self._token_expires = token, time.monotonic() + lifetime - 60
        return {"Authorization": f"Bearer {token}"}

    def _request(self, endpoint, params, allow_empty=False, *, live=False):
        for attempt in range(3):
            # Historical: 30/min. Authenticated live: 60/min; leave headroom.
            spacing = 1.1 if live else 2.1
            self.sleep(max(0, spacing - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                response = self.client.get(
                    self.base_url + endpoint,
                    params=params,
                    headers={
                        "User-Agent": "F1IntelligencePlatform/0.4.0",
                        **(self._authorization() if live else {}),
                    },
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
        observation_started_at = datetime.now(timezone.utc)
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
            return replace(
                normalize(data, source_session, drivers, datetime.now(timezone.utc)),
                observation_started_at=observation_started_at,
            )
        except (ValueError, TypeError, KeyError) as error:
            raise ProviderError("OpenF1 data is incomplete or inconsistent") from error

    def inspect_live_session(
        self, source_session: int, now: datetime, drivers: list[int] | None = None
    ) -> SessionCompletion:
        """Active status requires source signals, never the scheduled clock alone."""
        if source_session < 1 or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Positive source session and aware clock are required")
        if drivers is not None and (
            not drivers or len(drivers) > 32 or any(number < 1 for number in drivers)
        ):
            raise ValueError("Live scope requires 1-32 positive driver numbers")
        self._live_observation = None
        try:
            params = {"session_key": source_session}
            metadata = self._request("sessions", params, live=True)
            if len(metadata) != 1 or metadata[0]["session_key"] != source_session:
                raise ValueError
            row = metadata[0]
            cancelled = row.get("is_cancelled", False)
            start = timestamp(row["date_start"]) if row.get("date_start") else None
            end = timestamp(row["date_end"]) if row.get("date_end") else None
            if (
                not isinstance(cancelled, bool)
                or (not cancelled and start is None)
                or (start and end and end < start)
            ):
                raise ValueError
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
            # Bound detection so ancient starts cannot keep polling forever.
            if now < start or now > start + timedelta(hours=6):
                return SessionCompletion(**context)
            signals = self._request("race_control", params, allow_empty=True, live=True)
            statuses = []
            qualifying = context["session_type"] in {
                SessionType.QUALIFYING,
                SessionType.SPRINT_QUALIFYING,
            }
            for signal in signals:
                if signal["session_key"] != source_session:
                    raise ValueError
                observed = timestamp(signal["date"])
                if (
                    not start <= observed <= now
                    or signal.get("driver_number") is not None
                ):
                    continue
                message = signal.get("message", "").strip().upper()
                if signal.get("category") == "SessionStatus":
                    # Q1/Q2 ends do not finalize the full qualifying session.
                    if (
                        message == "SESSION ENDED"
                        and qualifying
                        and signal.get("qualifying_phase") != 3
                    ):
                        message = "PHASE ENDED"
                    statuses.append((observed, message))
                elif message == "GREEN LIGHT - PIT EXIT OPEN":
                    statuses.append((observed, "SESSION STARTED"))
                elif (
                    signal.get("flag") == "CHEQUERED"
                    and signal.get("scope") == "Track"
                    and (not qualifying or signal.get("qualifying_phase") == 3)
                ):
                    statuses.append((observed, "SESSION ENDED"))
            latest = max(statuses) if statuses else None
            active = bool(
                latest
                and latest[1]
                in {"SESSION STARTED", "SESSION RESUMED", "SESSION RESTARTED"}
            )
            cancelled = bool(latest and latest[1] == "SESSION CANCELLED")
            if (
                not active
                and not cancelled
                and drivers
                and (
                    latest is None
                    or latest[1]
                    not in {
                        "SESSION ENDED",
                        "SESSION STOPPED",
                        "SESSION ABORTED",
                        "PHASE ENDED",
                    }
                )
            ):
                # Some sessions lack start messages. Recent source telemetry can
                # prove activity, but cannot override a stop/end/cancellation.
                for number in sorted(set(drivers)):
                    recent = self._request(
                        "car_data",
                        {
                            **params,
                            "driver_number": number,
                            "date>=": max(
                                start, now - timedelta(seconds=120)
                            ).isoformat(),
                            "date<=": now.isoformat(),
                        },
                        allow_empty=True,
                        live=True,
                    )
                    for sample in recent:
                        if (
                            sample["session_key"] != source_session
                            or sample["driver_number"] != number
                        ):
                            raise ValueError
                        if (
                            max(start, now - timedelta(seconds=120))
                            <= timestamp(sample["date"])
                            <= now
                        ):
                            active = True
                    if active:
                        break
            if active:
                context["settled"] = False
            self._live_observation = (source_session, now, metadata, signals)
            return SessionCompletion(
                **context,
                active=active,
                cancelled=cancelled,
                observed_at=latest[0] if latest else None,
            )
        except (ValueError, TypeError, KeyError, AttributeError):
            raise ProviderError("OpenF1 live session metadata is invalid") from None

    def fetch_incremental(
        self, source_session: int, drivers: list[int], cursor: dict, now: datetime
    ):
        """Bounded time windows with overlap; small mutable summaries are rechecked.

        Only finalization fetches the complete history. Late corrections outside the
        overlap are intentionally provisional until that authoritative full refresh.
        """
        observation_started = datetime.now(timezone.utc)
        observation = self._live_observation
        if observation is None or observation[:2] != (source_session, now):
            raise ProviderError("A current live session inspection is required")
        _, _, metadata, signals = observation
        params = {"session_key": source_session}
        start = timestamp(metadata[0]["date_start"])
        previous = (
            timestamp(cursor["through"])
            if cursor.get("through")
            else max(start, now - timedelta(seconds=120))
        )
        if previous > now:
            raise ProviderError("Live cursor is ahead of the observation clock")
        through = min(now, previous + timedelta(seconds=300))
        lower = (
            max(start, previous - timedelta(seconds=120))
            if cursor.get("through")
            else previous
        )
        window = {"date>=": lower.isoformat(), "date<=": through.isoformat()}
        data = {
            "sessions": metadata,
            "drivers": self._request("drivers", params, live=True),
        }
        for endpoint in KINDS:
            data[endpoint] = []
            if endpoint == "race_control":
                data[endpoint] = [
                    row for row in signals if timestamp(row["date"]) <= now
                ]
            elif endpoint == "weather":
                data[endpoint] = self._request(
                    endpoint, {**params, **window}, allow_empty=True, live=True
                )
            else:
                for number in sorted(set(drivers)):
                    data[endpoint].extend(
                        self._request(
                            endpoint,
                            {
                                **params,
                                "driver_number": number,
                                **({} if endpoint in {"laps", "stints"} else window),
                            },
                            allow_empty=True,
                            live=True,
                        )
                    )
        try:
            return replace(
                normalize(
                    data,
                    source_session,
                    drivers,
                    datetime.now(timezone.utc),
                    provisional=True,
                ),
                observation_started_at=observation_started,
                cursor={"through": through.isoformat()},
            )
        except (ValueError, TypeError, KeyError):
            raise ProviderError(
                "OpenF1 live data is incomplete or inconsistent"
            ) from None

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

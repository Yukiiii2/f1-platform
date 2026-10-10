from datetime import date, datetime, timezone
from decimal import Decimal

from app.domain.enums import SessionStatus, SessionType
from app.ingestion.contracts import ImportBundle, NormalizedRecord

SESSION_FIELDS = {
    "FirstPractice": SessionType.PRACTICE_1,
    "SecondPractice": SessionType.PRACTICE_2,
    "ThirdPractice": SessionType.PRACTICE_3,
    "Qualifying": SessionType.QUALIFYING,
    "Sprint": SessionType.SPRINT,
    "SprintQualifying": SessionType.SPRINT_QUALIFYING,
    "SprintShootout": SessionType.SPRINT_QUALIFYING,
}


def schedule(source: dict) -> dict:
    scheduled = date.fromisoformat(source["date"])
    starts = None
    if source.get("time"):
        starts = datetime.fromisoformat(f"{source['date']}T{source['time']}")
        if starts.tzinfo is None:
            raise ValueError("Missing schedule timezone")
        starts = starts.astimezone(timezone.utc)
    return {"scheduled_date": scheduled, "starts_at": starts}


def gap_milliseconds(value: str | None) -> int | None:
    if not value or not value.startswith("+"):
        return None
    # Textual lap gaps are not time gaps.
    if "lap" in value.lower():
        return None
    seconds = Decimal(0)
    for component in value[1:].split(":"):
        seconds = seconds * 60 + Decimal(component)
    milliseconds = seconds * 1000
    if milliseconds != milliseconds.to_integral_value():
        raise ValueError("Gap has sub-millisecond precision")
    return int(milliseconds)


def normalize(
    data: dict,
    year: int,
    requested_round: int | None,
    *,
    observed_at: datetime | None = None,
) -> ImportBundle:
    records = {}

    def add(kind, external_id, attributes, references=None):
        previous = records.get((kind, external_id))
        # Preserve sparse identity fields, but explicit unavailable schedule/result
        # values must clear obsolete data from an earlier import.
        attributes = {
            key: value
            for key, value in attributes.items()
            if value is not None or key in {"starts_at", "position"} or kind == "result"
        }
        if previous:
            if kind == "result" and (
                previous.attributes != attributes
                or previous.references != (references or {})
            ):
                raise ValueError(
                    "Conflicting classifications for the same driver/session "
                    "are unsupported"
                )
            attributes = previous.attributes | attributes
            references = previous.references | (references or {})
        records[kind, external_id] = NormalizedRecord(
            kind, external_id, attributes, references or {}
        )

    def add_driver(source):
        key = source["driverId"]
        add(
            "driver",
            key,
            {
                "given_name": source["givenName"],
                "family_name": source["familyName"],
                "code": source.get("code"),
                "permanent_number": int(source["permanentNumber"])
                if source.get("permanentNumber")
                else None,
                "nationality": source.get("nationality"),
            },
        )
        return key

    def add_team(source):
        key = source["constructorId"]
        add(
            "team",
            key,
            {"name": source["name"], "nationality": source.get("nationality")},
        )
        return key

    def event_key(source):
        if int(source["season"]) != year:
            raise ValueError("Wrong source season")
        source_round = int(source["round"])
        if requested_round is not None and source_round != requested_round:
            raise ValueError("Wrong source round")
        return f"{year}:{source_round}"

    def add_race(source):
        key = event_key(source)
        circuit = source["Circuit"]
        add(
            "circuit",
            circuit["circuitId"],
            {
                "name": circuit["circuitName"],
                "country": circuit["Location"]["country"],
                "locality": circuit["Location"].get("locality"),
            },
        )
        add(
            "event",
            key,
            {
                "name": source["raceName"],
                "round": int(source["round"]),
                **schedule(source),
            },
            {
                "season_id": ("season", str(year)),
                "circuit_id": ("circuit", circuit["circuitId"]),
            },
        )
        add(
            "session",
            key + ":race",
            {"type": SessionType.RACE, **schedule(source)},
            {"event_id": ("event", key)},
        )
        for field, session_type in SESSION_FIELDS.items():
            if source.get(field):
                add(
                    "session",
                    key + ":" + session_type,
                    {"type": session_type, **schedule(source[field])},
                    {"event_id": ("event", key)},
                )
        return key

    add("season", str(year), {"year": year})
    if not data["races"]:
        raise ValueError("No source schedule for requested season/round")
    for source in data["races"]:
        add_race(source)
    for source in data["drivers"]:
        add_driver(source)
    for source in data["constructors"]:
        add_team(source)
    for endpoint, nested, session_type in [
        ("results", "Results", SessionType.RACE),
        ("qualifying", "QualifyingResults", SessionType.QUALIFYING),
        ("sprint", "SprintResults", SessionType.SPRINT),
    ]:
        for source in data[endpoint]:
            key = event_key(source)
            if ("event", key) not in records:
                key = add_race(source)
            session_key = key + ":" + session_type
            add(
                "session",
                session_key,
                {"type": session_type},
                {"event_id": ("event", key)},
            )
            if source[nested]:
                add("session", session_key, {"status": SessionStatus.COMPLETED})
            for result in source[nested]:
                driver_key = add_driver(result["Driver"])
                team_key = add_team(result["Constructor"])
                attributes = {
                    "position": int(result["position"])
                    if result.get("position")
                    else None
                }
                if session_type != SessionType.QUALIFYING:
                    time_data = result.get("Time", {})
                    attributes |= {
                        "grid_position": int(result["grid"])
                        if result.get("grid") is not None
                        else None,
                        "completed_laps": int(result["laps"])
                        if result.get("laps") is not None
                        else None,
                        "points": Decimal(result["points"])
                        if result.get("points") is not None
                        else None,
                        "status": result.get("status"),
                        "total_time_ms": int(time_data["millis"])
                        if time_data.get("millis") is not None
                        else None,
                        "gap_ms": gap_milliseconds(time_data.get("time")),
                    }
                add(
                    "result",
                    session_key + ":" + driver_key,
                    attributes,
                    {
                        "session_id": ("session", session_key),
                        "driver_id": ("driver", driver_key),
                        "team_id": ("team", team_key),
                    },
                )
    for endpoint, nested, kind in [
        ("driverstandings", "DriverStandings", "driver_standing"),
        ("constructorstandings", "ConstructorStandings", "constructor_standing"),
    ]:
        for snapshot in data[endpoint]:
            key = event_key(snapshot)
            if ("event", key) not in records:
                raise ValueError("Standings snapshot has no matching source event")
            for source in snapshot[nested]:
                if kind == "driver_standing":
                    identity = add_driver(source["Driver"])
                    ref = {"driver_id": ("driver", identity)}
                    for constructor in source.get("Constructors", []):
                        add_team(constructor)
                else:
                    identity = add_team(source["Constructor"])
                    ref = {"team_id": ("team", identity)}
                add(
                    kind,
                    key + ":" + identity,
                    {
                        "position": int(source["position"])
                        if source.get("position")
                        else None,
                        "points": Decimal(source["points"]),
                        "wins": int(source["wins"]),
                    },
                    {
                        "season_id": ("season", str(year)),
                        "event_id": ("event", key),
                        **ref,
                    },
                )
    return ImportBundle(
        list(records.values()),
        observed_at or datetime.now(timezone.utc),
        raw_payload=data,
    )

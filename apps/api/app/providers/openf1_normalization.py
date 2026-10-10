"""OpenF1 field names and value conventions terminate at this boundary."""

import hashlib
import json
import re
from datetime import timezone
from decimal import Decimal, InvalidOperation

from pydantic import AwareDatetime, TypeAdapter

from app.domain.enums import SessionType
from app.ingestion.telemetry_contracts import TelemetryBundle, TelemetryRecord

SESSION_TYPES = {
    "Practice 1": SessionType.PRACTICE_1,
    "Practice 2": SessionType.PRACTICE_2,
    "Practice 3": SessionType.PRACTICE_3,
    "Qualifying": SessionType.QUALIFYING,
    "Sprint Shootout": SessionType.SPRINT_QUALIFYING,
    "Sprint Qualifying": SessionType.SPRINT_QUALIFYING,
    "Sprint": SessionType.SPRINT,
    "Race": SessionType.RACE,
}
KINDS = {
    "laps": "lap",
    "car_data": "telemetry",
    "stints": "stint",
    "pit": "pit",
    "position": "position",
    "intervals": "interval",
    "race_control": "race_control",
    "weather": "weather",
}


def timestamp(value):
    return TypeAdapter(AwareDatetime).validate_python(value).astimezone(timezone.utc)


def number(value):
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("Invalid source number") from None
    if not result.is_finite():
        raise ValueError("Nonfinite source number")
    return result


def state(value, off, on):
    if value is None:
        return None
    if value == off:
        return False
    if value == on:
        return True
    raise ValueError("Unsupported source state")


def pedal(value):
    # The upstream feed uses 104 for unavailable/error pedal data, not 104%.
    # Keep it in the source payload; never guess a throttle value or brake state.
    return None if value == 104 else value


def gap(value):
    if value is None:
        return None, None
    if isinstance(value, str):
        match = re.fullmatch(r"\+(\d+) LAPS?", value)
        if match:
            return None, int(match[1])
    return number(value), None


def normalize(data, source_session, drivers, fetched_at, *, provisional=False):
    sessions = data["sessions"]
    if len(sessions) != 1 or sessions[0]["session_key"] != source_session:
        raise ValueError("Expected one matching source session")
    metadata = sessions[0]
    starts_at, ends_at = (
        timestamp(metadata["date_start"]),
        timestamp(metadata["date_end"])
        if metadata.get("date_end") is not None or not provisional
        else None,
    )
    if (ends_at is not None and ends_at < starts_at) or metadata.get("is_cancelled"):
        raise ValueError("Session is cancelled or has invalid boundaries")
    codes = {}
    for row in data["drivers"]:
        if row["session_key"] != source_session:
            raise ValueError("Source driver belongs to a different session")
        driver_number = row["driver_number"]
        if driver_number in codes:
            raise ValueError("Duplicate source driver")
        codes[driver_number] = row.get("name_acronym")
    if not set(drivers).issubset(codes):
        raise ValueError("Requested driver is absent from source session")
    records, seen = [], {}
    for endpoint, kind in KINDS.items():
        for row in data[endpoint]:
            if row["session_key"] != source_session:
                raise ValueError("Source record belongs to a different session")
            driver = row.get("driver_number")
            if driver is not None and driver not in drivers:
                if kind == "race_control":
                    # Other drivers are outside the explicitly selected scope.
                    continue
                raise ValueError("Unexpected driver in filtered source response")
            if kind not in {"race_control", "weather"} and driver is None:
                raise ValueError("Source driver is unavailable")
            attributes = {}
            if kind == "lap":
                attributes = {
                    "lap_number": row["lap_number"],
                    "starts_at": timestamp(row["date_start"])
                    if row.get("date_start")
                    else None,
                    "duration_seconds": number(row.get("lap_duration")),
                    "sector_1_seconds": number(row.get("duration_sector_1")),
                    "sector_2_seconds": number(row.get("duration_sector_2")),
                    "sector_3_seconds": number(row.get("duration_sector_3")),
                    "is_pit_out_lap": row.get("is_pit_out_lap"),
                    "start_time_is_approximate": True,
                }
                key = f"{driver}:lap:{row['lap_number']}"
            elif kind == "stint":
                attributes = {
                    "stint_number": row["stint_number"],
                    "lap_start": row.get("lap_start"),
                    "lap_end": row.get("lap_end"),
                    "compound": row.get("compound"),
                    "tyre_age_at_start": row.get("tyre_age_at_start"),
                }
                key = f"{driver}:stint:{row['stint_number']}"
            else:
                stamp = timestamp(row["date"])
                attributes["timestamp"] = stamp
                key = f"{driver}:{stamp.isoformat()}"
                if kind == "telemetry":
                    attributes.update(
                        speed_kph=number(row.get("speed")),
                        throttle_percent=number(pedal(row.get("throttle"))),
                        brake_applied=state(pedal(row.get("brake")), 0, 100),
                        gear=row.get("n_gear"),
                        rpm=row.get("rpm"),
                        drs_state=row.get("drs"),
                        lap_id=None,
                    )
                elif kind == "pit":
                    lane = row.get("lane_duration")
                    if lane is None:
                        lane = row.get("pit_duration")  # Documented deprecated alias.
                    attributes.update(
                        lap_number=row.get("lap_number"),
                        lane_duration_seconds=number(lane),
                        stop_duration_seconds=number(row.get("stop_duration")),
                    )
                elif kind == "position":
                    attributes["position"] = row.get("position")
                elif kind == "interval":
                    for source, target in (
                        ("gap_to_leader", "gap_to_leader"),
                        ("interval", "interval"),
                    ):
                        seconds, laps = gap(row.get(source))
                        attributes[target + "_seconds"] = seconds
                        attributes[target + "_laps"] = laps
                elif kind == "race_control":
                    for field in (
                        "category",
                        "message",
                        "flag",
                        "scope",
                        "lap_number",
                        "sector",
                        "qualifying_phase",
                    ):
                        attributes[field] = row.get(field)
                    # Multiple different messages may legitimately share a timestamp.
                    content = {
                        key: value
                        for key, value in attributes.items()
                        if key != "timestamp"
                    }
                    digest = hashlib.sha256(
                        json.dumps(content, sort_keys=True).encode()
                    ).hexdigest()
                    key += ":" + digest
                elif kind == "weather":
                    for source, target in (
                        ("air_temperature", "air_temperature_c"),
                        ("track_temperature", "track_temperature_c"),
                        ("humidity", "humidity_percent"),
                        ("pressure", "pressure_mbar"),
                        ("wind_speed", "wind_speed_mps"),
                    ):
                        attributes[target] = number(row.get(source))
                    attributes["rainfall"] = state(row.get("rainfall"), 0, 1)
                    attributes["wind_direction_degrees"] = row.get("wind_direction")
            identity = kind, key
            if identity in seen:
                if seen[identity] != row:
                    raise ValueError("Conflicting source records with one identity")
                continue
            seen[identity] = row
            records.append(TelemetryRecord(kind, key, attributes, dict(row), driver))
    return TelemetryBundle(
        records,
        fetched_at,
        int(metadata["year"]),
        SESSION_TYPES[metadata["session_name"]],
        starts_at,
        ends_at,
        metadata["country_name"],
        {driver: codes[driver] for driver in drivers},
    )

"""Read-only tools over existing application handlers and public DTOs."""

import json
from dataclasses import dataclass
from typing import Annotated, Callable, Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import AwareDatetime, Field, ValidationError

from app import models, schemas
from app.ai.client import strict_schema
from app.api import core, strategy, telemetry
from app.schemas import telemetry as reads
from app.schemas.ai import BoundedComparison as Comparison
from app.schemas.ai import Evidence, PageContext
from app.schemas.comparison import CompareRequest
from app.schemas.domain import Schema


class Page(Schema):
    limit: Annotated[int, Field(ge=1, le=200)] = 50
    offset: Annotated[int, Field(ge=0)] = 0


class DriverID(Schema):
    driver_id: UUID


class EventID(Schema):
    event_id: UUID


class SessionID(Schema):
    session_id: UUID


class LapID(Schema):
    lap_id: UUID


class StintID(Schema):
    stint_id: UUID


class Events(Page):
    season: Annotated[int, Field(ge=1950)] | None = None


class Sessions(Page, EventID):
    pass


class Results(Page, SessionID):
    pass


class SessionPage(Results):
    provider: Annotated[str, Field(min_length=1, max_length=50)] | None = None


class DriverPage(SessionPage):
    driver_id: UUID | None = None


class TelemetryPage(DriverPage):
    from_time: AwareDatetime | None = None
    to_time: AwareDatetime | None = None


class LapTelemetry(Page, LapID):
    pass


class StintAge(StintID):
    completed_lap: Annotated[int, Field(ge=0)]


class Standings(Page):
    kind: Literal["drivers", "constructors"] = "drivers"
    season: Annotated[int, Field(ge=1950)]
    event_id: UUID | None = None


class Strategy(SessionID):
    provider: Annotated[str, Field(min_length=1, max_length=50)] | None = None


@dataclass(frozen=True)
class Tool:
    arguments: type[Schema]
    read: Callable
    dto: type[Schema] | None
    description: str


def stint(db, stint_id):
    return core.require(db, models.Stint, stint_id)


def standings(db, kind, **arguments):
    handler = core.driver_standings if kind == "drivers" else core.constructor_standings
    dto = (
        schemas.DriverStandingRead
        if kind == "drivers"
        else schemas.ConstructorStandingRead
    )
    return [dto.model_validate(row) for row in handler(db, **arguments)]


TOOLS = {
    "get_drivers": Tool(
        Page,
        core.drivers,
        schemas.DriverRead,
        "List recorded drivers; paginate to find a domain UUID.",
    ),
    "get_driver": Tool(
        DriverID, core.driver, schemas.DriverRead, "Read a driver by application UUID."
    ),
    "get_events": Tool(
        Events,
        core.events,
        schemas.EventRead,
        "List recorded events, optionally by season year.",
    ),
    "get_event": Tool(
        EventID, core.event, schemas.EventRead, "Read an event by application UUID."
    ),
    "get_sessions": Tool(
        Sessions,
        core.sessions,
        schemas.SessionRead,
        "List an event's recorded sessions.",
    ),
    "get_session": Tool(
        SessionID,
        core.session,
        schemas.SessionRead,
        "Read recorded session type and completion status.",
    ),
    "get_results": Tool(
        Results,
        core.results,
        schemas.ResultRead,
        "Read normalized session results; nulls are unknown.",
    ),
    "get_laps": Tool(
        DriverPage,
        telemetry.laps,
        reads.LapRead,
        "Read recorded laps and sector durations; "
        "paginate before best/aggregate claims.",
    ),
    "get_lap": Tool(
        LapID,
        telemetry.lap,
        reads.LapRead,
        "Read a selected lap; approximate starts are estimates.",
    ),
    "get_telemetry": Tool(
        TelemetryPage,
        telemetry.telemetry,
        reads.TelemetrySampleRead,
        "Read source speed, throttle, brake state, gear, RPM and DRS codes. "
        "Nulls are unknown; no team-only channels.",
    ),
    "get_lap_telemetry": Tool(
        LapTelemetry,
        telemetry.lap_telemetry,
        reads.TelemetrySampleRead,
        "Read only confirmed lap-associated samples; "
        "use compare_laps for explicitly permitted approximate windows.",
    ),
    "get_stints": Tool(
        DriverPage,
        telemetry.stints,
        reads.StintRead,
        "Read source stint bounds, compound and starting tyre age.",
    ),
    "get_stint": Tool(StintID, stint, reads.StintRead, "Read a selected source stint."),
    "get_stint_age": Tool(
        StintAge,
        telemetry.stint_tyre_age,
        None,
        "Calculate tyre age using completed-laps-v1 and source starting age.",
    ),
    "get_pits": Tool(
        DriverPage,
        telemetry.pits,
        reads.PitStopRead,
        "Read source pit stops; lane and stationary durations are different.",
    ),
    "get_positions": Tool(
        DriverPage,
        telemetry.positions,
        reads.PositionSampleRead,
        "Read source race positions, not spatial coordinates.",
    ),
    "get_intervals": Tool(
        DriverPage,
        telemetry.intervals,
        reads.IntervalSampleRead,
        "Read source interval/gap values, keeping lap and second units separate.",
    ),
    "get_standings": Tool(
        Standings,
        standings,
        None,
        "Read a recorded driver or constructor standings snapshot.",
    ),
    "get_race_control": Tool(
        DriverPage,
        telemetry.race_control,
        reads.RaceControlMessageRead,
        "Read source race-control messages including SC/VSC; "
        "never infer complete deployment periods.",
    ),
    "get_weather": Tool(
        SessionPage,
        telemetry.weather,
        reads.WeatherSampleRead,
        "Read recorded weather, not tyre temperatures.",
    ),
    "get_strategy": Tool(
        Strategy,
        strategy.strategy,
        None,
        "Read completed-race source stints/pits/SC context and calculated "
        "tyre ages/observed non-pit pace. No confirmed intent.",
    ),
    "compare_laps": Tool(
        Comparison,
        lambda db, **args: telemetry.compare(db, CompareRequest(**args)),
        None,
        "Compare recorded laps with A-B timing deltas (positive A slower). "
        "Interpolated traces are derived or estimated, never source channels.",
    ),
}


def separate_lap(lap):
    """Keep estimated window starts outside the source classification."""
    source = dict(lap)
    estimate = {}
    if source["start_time_is_approximate"]:
        estimate = {"lap_id": source["id"], "starts_at": source["starts_at"]}
        source["starts_at"] = None
    return source, estimate


def classify(name, value):
    if name in {"get_laps", "get_lap"}:
        pairs = (
            [separate_lap(row) for row in value]
            if isinstance(value, list)
            else [separate_lap(value)]
        )
        return {
            "source": [pair[0] for pair in pairs]
            if isinstance(value, list)
            else pairs[0][0],
            "estimate": {"lap_starts": [pair[1] for pair in pairs if pair[1]]},
        }
    if name == "get_strategy":
        source = {
            "session_id": value["session_id"],
            "drivers": [],
            "race_control": value["race_control"],
        }
        derived = {"lap_axis_end": value["lap_axis_end"], "drivers": []}
        for driver in value["drivers"]:
            identity = {key: driver[key] for key in ("driver_id", "provider")}
            source["drivers"].append(
                identity
                | {
                    "stints": [row["source"] for row in driver["stints"]],
                    "pits": driver["pits"],
                }
            )
            derived["drivers"].append(
                identity
                | {
                    "recorded_lap_count": driver["recorded_lap_count"],
                    "stints": [
                        {key: val for key, val in row.items() if key != "source"}
                        | {"stint_id": row["source"]["id"]}
                        for row in driver["stints"]
                    ],
                }
            )
        return {"source": source, "derived": derived}
    if name == "compare_laps":
        source, derived, estimate = {}, {}, {}
        tyre_fields = {
            "stint_id",
            "compound",
            "lap_start",
            "lap_end",
            "tyre_age_at_start",
        }
        for side in ("lap_a", "lap_b"):
            lap, lap_estimate = separate_lap(value[side]["lap"])
            tyres = value[side]["tyres"]
            source[side] = {
                "lap": lap,
                "tyres": {key: val for key, val in tyres.items() if key in tyre_fields},
            }
            derived[side] = {
                "tyres": {
                    key: val for key, val in tyres.items() if key not in tyre_fields
                }
            }
            if lap_estimate:
                estimate[side] = lap_estimate
        derived.update(
            {
                key: val
                for key, val in value.items()
                if key not in {"lap_a", "lap_b", "trace"}
            }
        )
        (estimate if value["trace"]["classification"] == "estimate" else derived)[
            "trace"
        ] = value["trace"]
        return {"source": source, "derived": derived, "estimate": estimate}
    if name == "get_stint_age":
        return {
            "source": {
                "stint_id": value["stint_id"],
                "tyre_age_at_start": value["tyre_age_at_start"],
            },
            "derived": {
                key: val for key, val in value.items() if key != "tyre_age_at_start"
            },
        }
    return {"source": value}


class ToolExecutor:
    def __init__(self, db, context: PageContext):
        self.db, self.context, self.evidence = db, context, []

    def definitions(self):
        return [
            {
                "type": "function",
                "name": name,
                "description": tool.description,
                "strict": True,
                "parameters": strict_schema(tool.arguments.model_json_schema()),
            }
            for name, tool in TOOLS.items()
        ]

    def execute(self, name, arguments):
        evidence = Evidence(
            id=f"e{len(self.evidence) + 1}",
            tool=name,
            arguments={},
            status="unavailable",
        )
        self.evidence.append(evidence)
        tool = TOOLS.get(name)
        if tool is None:
            evidence.error = "unknown_tool"
            return evidence
        try:
            parsed = tool.arguments.model_validate(arguments)
        except ValidationError:
            evidence.error = "invalid_arguments"
            return evidence
        evidence.arguments = parsed.model_dump(mode="json")
        if (
            name == "compare_laps"
            and parsed.allow_approximate
            and not (
                self.context.allow_approximate
                or (
                    self.context.comparison
                    and self.context.comparison.allow_approximate
                )
            )
        ):
            evidence.error = "approximate_opt_in_required"
            return evidence
        args = parsed.model_dump()
        paged = isinstance(parsed, Page)
        if paged:
            args["limit"] += 1
        try:
            value = tool.read(self.db, **args)
        except HTTPException as error:
            if error.status_code not in {404, 422}:
                raise
            evidence.error = (
                "record_not_found"
                if error.status_code == 404
                else "data_context_unavailable"
            )
            return evidence
        if paged:
            evidence.truncated = len(value) > parsed.limit
            if evidence.truncated:
                evidence.next_offset = parsed.offset + parsed.limit
            value = value[: parsed.limit]
        if isinstance(value, list):
            if not value:
                evidence.error = "no_records"
                return evidence
            value = [
                (tool.dto.model_validate(row) if tool.dto else row).model_dump(
                    mode="json"
                )
                for row in value
            ]
        else:
            value = (tool.dto.model_validate(value) if tool.dto else value).model_dump(
                mode="json"
            )
        data = classify(name, value)
        if len(json.dumps(data)) > 120000:
            evidence.error = "result_too_large_use_narrower_query"
            return evidence
        evidence.status, evidence.data = "available", data
        return evidence

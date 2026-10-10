from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field

from app.schemas.comparison import CompareRequest
from app.schemas.domain import Schema


class BoundedComparison(CompareRequest):
    sample_count: Annotated[int, Field(ge=2, le=201)] = 201


class PageContext(Schema):
    route: Annotated[str, Field(max_length=300)] | None = None
    event_id: UUID | None = None
    session_id: UUID | None = None
    driver_id: UUID | None = None
    lap_id: UUID | None = None
    stint_id: UUID | None = None
    season: Annotated[int, Field(ge=1950, le=2100)] | None = None
    comparison: BoundedComparison | None = None
    allow_approximate: bool = False


class QueryRequest(Schema):
    question: Annotated[str, Field(min_length=1, max_length=4000)]
    context: PageContext = Field(default_factory=PageContext)


class Reference(Schema):
    evidence_id: Annotated[str, Field(min_length=1, max_length=20)]
    pointer: Annotated[
        str, Field(pattern=r"^/(source|derived|estimate)(/.*)?$", max_length=500)
    ]


class InterpretationDraft(Schema):
    kind: Literal["observed_pace", "pit_timing", "tyre_context", "lap_comparison"]
    evidence_ids: Annotated[list[str], Field(min_length=1, max_length=12)]


class AnswerDraft(Schema):
    facts: Annotated[list[Reference], Field(max_length=20)]
    calculations: Annotated[list[Reference], Field(max_length=20)]
    estimates: Annotated[list[Reference], Field(max_length=20)]
    interpretations: Annotated[list[InterpretationDraft], Field(max_length=5)]
    unavailable: Annotated[list[Reference], Field(max_length=20)]


class Evidence(Schema):
    id: str
    tool: str
    arguments: dict[str, Any]
    status: Literal["available", "unavailable"]
    data: dict[str, Any] = Field(default_factory=dict)
    data_status: Literal["not_tracked", "provisional", "finalized"] = "not_tracked"
    truncated: bool = False
    next_offset: int | None = None
    error: str | None = None


class GroundedValue(Reference):
    value: Any
    classification: Literal["source", "derived", "estimate"]


class Interpretation(InterpretationDraft):
    text: str
    classification: Literal["interpretation"] = "interpretation"
    uncertainty: Literal["not_confirmed_team_intent"] = "not_confirmed_team_intent"


class QueryResponse(Schema):
    status: Literal["answered", "unavailable"]
    facts: list[GroundedValue] = Field(default_factory=list)
    calculations: list[GroundedValue] = Field(default_factory=list)
    estimates: list[GroundedValue] = Field(default_factory=list)
    interpretations: list[Interpretation] = Field(default_factory=list)
    unavailable: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    policy_version: Literal["pitwall-tool-first-v1"] = "pitwall-tool-first-v1"

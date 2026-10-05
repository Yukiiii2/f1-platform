"""Read-only comparison over the Phase 4 application models."""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import or_, select

from app import models
from app.schemas.comparison import (
    Channels,
    ComparedLap,
    CompareRequest,
    CompareResponse,
    LapSummary,
    SectorDeltas,
    TyreContext,
)
from app.telemetry.comparison import MAX_GAP, LapTrace, TimedSample, align_traces
from app.telemetry.tyres import tyre_age

MAX_SOURCE_SAMPLES = 50000


class ComparisonError(ValueError):
    pass


class LapNotFound(LookupError):
    pass


def difference_ms(a, b):
    if a is None or b is None or a <= 0 or b <= 0:
        return None
    return (a - b) * 1000


def tyre_context(db, lap) -> TyreContext:
    stints = list(
        db.scalars(
            select(models.Stint).where(
                models.Stint.session_id == lap.session_id,
                models.Stint.driver_id == lap.driver_id,
                models.Stint.provider == lap.provider,
            )
        )
    )
    matching = [
        row
        for row in stints
        if row.lap_start is not None
        and row.lap_end is not None
        and row.lap_start <= lap.lap_number <= row.lap_end
    ]
    uncertain = any(
        row.lap_start is None
        or (row.lap_start <= lap.lap_number and row.lap_end is None)
        for row in stints
    )
    if len(matching) > 1:
        return TyreContext(status="ambiguous")
    if not matching or uncertain:
        return TyreContext()
    stint = matching[0]
    before, age_before = tyre_age(
        stint.tyre_age_at_start, stint.lap_start, stint.lap_end, lap.lap_number - 1
    )
    after, age_after = tyre_age(
        stint.tyre_age_at_start, stint.lap_start, stint.lap_end, lap.lap_number
    )
    return TyreContext(
        status="available",
        stint_id=stint.id,
        compound=stint.compound,
        lap_start=stint.lap_start,
        lap_end=stint.lap_end,
        tyre_age_at_start=stint.tyre_age_at_start,
        completed_laps_before=before,
        completed_laps_after=after,
        total_age_before=age_before,
        total_age_after=age_after,
    )


def lap_trace(db, lap, allow_approximate) -> LapTrace:
    duration = lap.duration_seconds
    if duration is None or duration <= 0 or lap.starts_at is None:
        return LapTrace(duration, [], "unavailable", ["lap_time_or_start_unavailable"])
    if lap.start_time_is_approximate and not allow_approximate:
        return LapTrace(
            duration, [], "unavailable", ["approximate_start_requires_opt_in"]
        )
    sample = models.TelemetrySample
    query = select(sample).where(
        sample.session_id == lap.session_id,
        sample.driver_id == lap.driver_id,
        sample.provider == lap.provider,
    )
    # Decimal durations convert to timestamp microseconds without float arithmetic.
    end = lap.starts_at + timedelta(microseconds=int(duration * 1000000))
    margin = timedelta(microseconds=int(MAX_GAP * 1000000))
    query = query.where(
        sample.timestamp >= lap.starts_at - margin, sample.timestamp <= end + margin
    )
    if allow_approximate:
        query = query.where(or_(sample.lap_id == lap.id, sample.lap_id.is_(None)))
    else:
        query = query.where(sample.lap_id == lap.id)
    rows = list(
        db.scalars(query.order_by(sample.timestamp).limit(MAX_SOURCE_SAMPLES + 1))
    )
    if len(rows) > MAX_SOURCE_SAMPLES:
        raise ComparisonError("Selected lap exceeds the comparison sample limit")
    if not rows:
        return LapTrace(duration, [], "unavailable", ["no_eligible_samples"])
    approximate = lap.start_time_is_approximate or any(
        row.lap_id is None for row in rows
    )
    samples = []
    for row in rows:
        elapsed = row.timestamp - lap.starts_at
        seconds = (
            Decimal(elapsed.days * 86400 + elapsed.seconds)
            + Decimal(elapsed.microseconds) / 1000000
        )
        samples.append(TimedSample(seconds, Channels.model_validate(row)))
    return LapTrace(
        duration,
        samples,
        "approximate_window" if approximate else "confirmed",
        ["approximate_lap_window"] if approximate else [],
    )


def compare_laps(db, request: CompareRequest) -> CompareResponse:
    a, b = db.get(models.Lap, request.lap_a_id), db.get(models.Lap, request.lap_b_id)
    if a is None or b is None:
        raise LapNotFound("Lap not found")
    if a.session_id != b.session_id:
        raise ComparisonError("Comparison requires two laps from the same session")
    trace_a, trace_b = (
        lap_trace(db, a, request.allow_approximate),
        lap_trace(db, b, request.allow_approximate),
    )
    return CompareResponse(
        lap_a=ComparedLap(lap=LapSummary.model_validate(a), tyres=tyre_context(db, a)),
        lap_b=ComparedLap(lap=LapSummary.model_validate(b), tyres=tyre_context(db, b)),
        lap_delta_ms=difference_ms(a.duration_seconds, b.duration_seconds),
        sector_delta_ms=SectorDeltas(
            **{
                f"sector_{index}": difference_ms(
                    getattr(a, f"sector_{index}_seconds"),
                    getattr(b, f"sector_{index}_seconds"),
                )
                for index in range(1, 4)
            }
        ),
        trace=align_traces(trace_a, trace_b, request.alignment, request.sample_count),
    )

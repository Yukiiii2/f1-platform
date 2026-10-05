"""Pure resampling of copied source values. Never assigns or changes raw samples.

Distance is trapezoidal speed integration (km/h / 3.6 -> m/s), normalized
independently for each complete lap. Elapsed time is linearly interpolated between
distance knots. Interior plateaus select first arrival; endpoints retain the lap
start/finish times. This coordinate is not track GPS.
If speed coverage is incomplete, use a common elapsed-time axis without a delta
trace: equal elapsed time does not establish equal track position.

Continuous channels interpolate linearly between adjacent source rows. Discrete
channels hold the previous value. Neither crosses gaps over one second or extends
beyond source coverage; explicit null values stay unknown. Results are derived,
or estimates when samples are selected using approximate lap windows.
"""

from bisect import bisect_left
from dataclasses import dataclass
from decimal import Decimal

from app.schemas.comparison import AlignedTrace, Channels, TracePoint

MAX_GAP = Decimal("1")
PRECISION = Decimal("0.000001")
CONTINUOUS = ("speed_kph", "throttle_percent", "rpm")
DISCRETE = ("brake_applied", "gear", "drs_state")


@dataclass(frozen=True)
class TimedSample:
    elapsed: Decimal
    channels: Channels


@dataclass(frozen=True)
class LapTrace:
    duration: Decimal | None
    samples: list[TimedSample]
    association: str
    warnings: list[str]


class Timeline:
    def __init__(self, trace: LapTrace):
        self.trace = trace
        self.samples = sorted(trace.samples, key=lambda row: row.elapsed)
        self.times = [row.elapsed for row in self.samples]

    def at(self, elapsed: Decimal | None) -> Channels:
        duration = self.trace.duration
        if elapsed is None or duration is None or elapsed < 0 or elapsed > duration:
            return Channels()
        index = bisect_left(self.times, elapsed)
        if index < len(self.times) and self.times[index] == elapsed:
            return self.samples[index].channels
        if index == 0 or index == len(self.times):
            return Channels()
        left, right = self.samples[index - 1], self.samples[index]
        gap = right.elapsed - left.elapsed
        if gap <= 0 or gap > MAX_GAP:
            return Channels()
        fraction = (elapsed - left.elapsed) / gap
        values = {}
        for field in CONTINUOUS:
            a, b = getattr(left.channels, field), getattr(right.channels, field)
            values[field] = (
                None
                if a is None or b is None
                else (a + (b - a) * fraction).quantize(PRECISION)
            )
        for field in DISCRETE:
            values[field] = getattr(left.channels, field)
        return Channels(**values)

    def distance(self):
        duration = self.trace.duration
        if duration is None or duration <= 0 or not self.times:
            return None
        times = [
            Decimal(0),
            *(time for time in self.times if 0 < time < duration),
            duration,
        ]
        speeds = [self.at(time).speed_kph for time in times]
        if any(speed is None or speed < 0 for speed in speeds):
            return None
        distances = [Decimal(0)]
        for index in range(1, len(times)):
            gap = times[index] - times[index - 1]
            if gap > MAX_GAP:
                return None
            meters = (speeds[index - 1] + speeds[index]) / Decimal("7.2") * gap
            distances.append(distances[-1] + meters)
        if distances[-1] <= 0:
            return None
        return times, distances


def distance_time(distance_curve, fraction):
    times, distances = distance_curve
    if fraction == 1:
        return times[-1]
    target = distances[-1] * fraction
    index = bisect_left(distances, target)
    if index == 0:
        return times[0]
    if distances[index] == target:
        return times[index]
    weight = (target - distances[index - 1]) / (distances[index] - distances[index - 1])
    return (times[index - 1] + (times[index] - times[index - 1]) * weight).quantize(
        PRECISION
    )


def align_traces(a: LapTrace, b: LapTrace, alignment: str, count: int) -> AlignedTrace:
    result = AlignedTrace(
        requested_alignment=alignment,
        association_a=a.association,
        association_b=b.association,
        sample_count_a=len(a.samples),
        sample_count_b=len(b.samples),
        classification="estimate"
        if "approximate_window" in (a.association, b.association)
        else "derived",
        warnings=[
            *("a:" + warning for warning in a.warnings),
            *("b:" + warning for warning in b.warnings),
        ],
    )
    if a.duration is None or b.duration is None or a.duration <= 0 or b.duration <= 0:
        result.warnings.append("lap_duration_unavailable_or_nonpositive")
        return result
    if not a.samples and not b.samples:
        result.warnings.append("samples_unavailable")
        return result
    ta, tb = Timeline(a), Timeline(b)
    da, db = ta.distance(), tb.distance()
    use_distance = (
        alignment == "normalized_distance" and da is not None and db is not None
    )
    if alignment == "normalized_distance" and not use_distance:
        result.warnings.append("incomplete_speed_coverage_elapsed_time_fallback")
    result.alignment = "normalized_distance" if use_distance else "elapsed_time"
    result.axis = (
        "fraction_of_integrated_distance" if use_distance else "elapsed_seconds"
    )
    result.delta_available = use_distance
    if use_distance:
        result.distance_method = "trapezoidal_speed_integration"
        result.distance_a_m = da[1][-1].quantize(PRECISION)
        result.distance_b_m = db[1][-1].quantize(PRECISION)
    span = Decimal(1) if use_distance else max(a.duration, b.duration)
    result.sample_resolution = span / (count - 1)
    for index in range(count):
        coordinate = span * index / (count - 1)
        if use_distance:
            ea, eb = distance_time(da, coordinate), distance_time(db, coordinate)
        else:
            ea = coordinate if coordinate <= a.duration else None
            eb = coordinate if coordinate <= b.duration else None
        result.points.append(
            TracePoint(
                coordinate=coordinate,
                elapsed_seconds_a=ea,
                elapsed_seconds_b=eb,
                delta_ms=(ea - eb) * 1000 if use_distance else None,
                channels_a=ta.at(ea),
                channels_b=tb.at(eb),
            )
        )
    complete = all(
        value is not None
        for point in result.points
        for channels in (point.channels_a, point.channels_b)
        for value in channels.model_dump().values()
    )
    any_data = any(
        value is not None
        for point in result.points
        for channels in (point.channels_a, point.channels_b)
        for value in channels.model_dump().values()
    )
    result.availability = (
        "available" if complete else "partial" if any_data else "unavailable"
    )
    if not complete:
        result.warnings.append("missing_channels_or_sample_gaps")
    return result

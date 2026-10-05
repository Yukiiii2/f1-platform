def tyre_age(
    age_at_start: int | None,
    lap_start: int,
    lap_end: int | None,
    completed_lap: int,
) -> tuple[int, int | None]:
    """Age after completing a lap; lap_start is the first lap driven on this set.

    completed-laps-v1: usage = min(completed_lap, lap_end) - lap_start + 1.
    At lap_start - 1 usage is zero. Missing pre-stint age stays unknown.
    A request past lap_end describes the set's final age, not subsequent usage.
    """
    if lap_start < 1 or completed_lap < lap_start - 1:
        raise ValueError("Completed lap precedes this stint")
    if lap_end is not None and lap_end < lap_start:
        raise ValueError("Stint lap boundaries are reversed")
    if age_at_start is not None and age_at_start < 0:
        raise ValueError("Tyre age cannot be negative")
    last = min(completed_lap, lap_end) if lap_end is not None else completed_lap
    usage = last - lap_start + 1
    return usage, None if age_at_start is None else age_at_start + usage

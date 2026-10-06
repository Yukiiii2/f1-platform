"""Read-only strategy: source context and deterministic observed pace/tyre ages."""

import re
from decimal import Decimal

from sqlalchemy import select

from app import models
from app.schemas.strategy import (
    DriverStrategyRead,
    PaceRead,
    StrategyRead,
    StrategyStintRead,
)
from app.telemetry.tyres import tyre_age


def session_strategy(db, session, provider=None):
    def rows(model, order):
        query = select(model).where(model.session_id == session.id)
        if provider is not None:
            query = query.where(model.provider == provider)
        return list(db.scalars(query.order_by(getattr(model, order), model.id)))

    laps = rows(models.Lap, "lap_number")
    stints = rows(models.Stint, "stint_number")
    pits = rows(models.PitStop, "timestamp")
    messages = rows(models.RaceControlMessage, "timestamp")
    scopes = sorted({(row.driver_id, row.provider) for row in [*laps, *stints, *pits]})
    drivers = []
    for driver_id, source in scopes:

        def scoped(records):
            return [
                row
                for row in records
                if row.driver_id == driver_id and row.provider == source
            ]

        driver_laps, driver_stints, driver_pits = (
            scoped(laps),
            scoped(stints),
            scoped(pits),
        )
        pit_context = all(pit.lap_number is not None for pit in driver_pits)
        # A source pit lap and the following lap may include pit-lane running.
        # No timestamp-to-lap inference when the source pit lap is missing.
        pit_laps = {
            number
            for pit in driver_pits
            if pit.lap_number is not None
            for number in (pit.lap_number, pit.lap_number + 1)
        }
        summaries = []
        for stint in driver_stints:
            complete = stint.lap_start is not None and stint.lap_end is not None
            ambiguous = complete and any(
                other.id != stint.id
                and (
                    other.lap_start is None
                    or other.lap_end is None
                    or (
                        other.lap_start <= stint.lap_end
                        and other.lap_end >= stint.lap_start
                    )
                )
                for other in driver_stints
            )
            status = (
                "unavailable"
                if not complete
                else "ambiguous"
                if ambiguous
                else "available"
            )
            observed = [
                lap
                for lap in driver_laps
                if complete and stint.lap_start <= lap.lap_number <= stint.lap_end
            ]
            # Shared source boundary laps are not assigned to either stint.
            unique = [
                lap
                for lap in observed
                if not any(
                    other.id != stint.id
                    and (
                        other.lap_start is None
                        or other.lap_end is None
                        or other.lap_start <= lap.lap_number <= other.lap_end
                    )
                    for other in driver_stints
                )
            ]
            timings = [
                lap.duration_seconds
                for lap in unique
                if pit_context
                and lap.duration_seconds is not None
                and lap.duration_seconds > 0
                and lap.is_pit_out_lap is False
                and lap.lap_number not in pit_laps
            ]
            usage, age = (None, None)
            completed_lap = (
                stint.lap_end
                if status == "available"
                else max(
                    (
                        lap.lap_number
                        for lap in unique
                        if lap.duration_seconds is not None and lap.duration_seconds > 0
                    ),
                    default=None,
                )
            )
            if completed_lap is not None:
                usage, age = tyre_age(
                    stint.tyre_age_at_start,
                    stint.lap_start,
                    stint.lap_end,
                    completed_lap,
                )
            summaries.append(
                StrategyStintRead(
                    source=stint,
                    context_status=status,
                    age_completed_lap=completed_lap,
                    completed_laps_on_stint=usage,
                    total_tyre_age=age,
                    pace=PaceRead(
                        recorded_laps=len(observed),
                        included_laps=len(timings),
                        excluded_laps=len(observed) - len(timings),
                        average_seconds=(sum(timings) / len(timings)).quantize(
                            Decimal("0.000001")
                        )
                        if timings
                        else None,
                        best_seconds=min(timings) if timings else None,
                        unavailable_reason=(
                            None
                            if timings
                            else "stint_context"
                            if not unique
                            else "pit_lap_context"
                            if not pit_context
                            else "no_eligible_laps"
                        ),
                    ),
                )
            )
        drivers.append(
            DriverStrategyRead(
                driver_id=driver_id,
                provider=source,
                recorded_lap_count=len(driver_laps),
                stints=summaries,
                pits=driver_pits,
            )
        )
    axis = [lap.lap_number for lap in laps]
    axis.extend(stint.lap_end for stint in stints if stint.lap_end is not None)
    axis.extend(pit.lap_number for pit in pits if pit.lap_number is not None)
    context = [
        message
        for message in messages
        if message.category == "SafetyCar"
        or message.flag in {"SC", "VSC"}
        or re.search(r"\b(?:SAFETY CAR|VSC)\b", message.message, re.IGNORECASE)
    ]
    return StrategyRead(
        session_id=session.id,
        lap_axis_end=max(axis) if axis else None,
        drivers=drivers,
        race_control=context,
    )

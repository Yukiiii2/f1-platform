import type { Driver } from "../_lib/contracts";
import type {
  DriverStrategy,
  Strategy,
  StrategyStint,
} from "../_lib/strategy-contracts";
import { driverName, formatDuration, formatSchedule } from "../_lib/format";
import {
  lapPosition,
  stintSpan,
  stintLanes,
  strategyKey,
} from "../_lib/strategy";
import { channelNumber } from "../_lib/telemetry";
import { EmptyState, SectionHeading, TableRegion } from "../_components/ui";

function seconds(value: string | null) {
  const number = channelNumber(value);
  return number === null ? "Unavailable" : `${number.toFixed(3)} s`;
}
function paceTime(value: string | null) {
  const number = channelNumber(value);
  return number === null
    ? "Unavailable"
    : formatDuration(Math.round(number * 1000));
}
function compoundClass(value: string | null) {
  return ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"].includes(value ?? "")
    ? `compound-${value!.toLowerCase()}`
    : "compound-unknown";
}
function contextNote(stint: StrategyStint) {
  if (stint.context_status === "ambiguous")
    return "Source stint bounds overlap or neighbouring bounds are unknown. Shared laps are excluded from pace; ages use the reported snapshot lap.";
  if (stint.context_status === "unavailable")
    return "Source boundaries incomplete. Calculations unavailable.";
  if (stint.pace.unavailable_reason === "pit_lap_context")
    return "A source pit lap is unknown. Pace unavailable.";
  if (stint.pace.unavailable_reason === "no_eligible_laps")
    return "No eligible timed non-pit laps. Pace unavailable.";
  return null;
}

export function StrategyView({
  strategy,
  selected,
  drivers,
}: {
  strategy: Strategy;
  selected: DriverStrategy[];
  drivers: Map<string, Driver>;
}) {
  const name = (row: DriverStrategy) => driverName(drivers.get(row.driver_id)!);
  const controls = strategy.race_control.filter((row) =>
    selected.some(
      (driver) =>
        driver.provider === row.provider &&
        (row.driver_id === null || driver.driver_id === row.driver_id),
    ),
  );
  const axis = strategy.lap_axis_end;
  const controlGroups = new Map<
    number,
    { row: (typeof controls)[number]; index: number; count: number }
  >();
  controls.forEach((row, index) => {
    if (row.lap_number === null) return;
    const group = controlGroups.get(row.lap_number);
    if (group) group.count += 1;
    else controlGroups.set(row.lap_number, { row, index, count: 1 });
  });
  return (
    <>
      <section aria-label="Compared stint timelines">
        <SectionHeading title="Stint sequence" />
        <p className="section-note">
          Source compounds and lap boundaries. Pit markers sit on the reported
          lap, not an inferred instant. Blank portions have no plotted stint.
          All selected drivers share the recorded lap axis.
        </p>
        {axis === null ? (
          <EmptyState title="Lap axis unavailable">
            <p>
              No source lap numbers are available. Recorded details remain
              below.
            </p>
          </EmptyState>
        ) : (
          <div
            className="strategy-timeline-region"
            role="region"
            tabIndex={0}
            aria-label="Stint timelines; scroll horizontally on smaller screens"
          >
            <div className="strategy-timelines">
              {controls.some((row) => row.lap_number !== null) && (
                <div className="strategy-timeline-row">
                  <div className="strategy-row-label">
                    Race control{" "}
                    <span className="cell-detail">Source messages</span>
                  </div>
                  <div className="strategy-control-track">
                    {[...controlGroups.values()].map(
                      ({ row, index, count }, lane) => {
                        const position = lapPosition(row.lap_number, axis);
                        return position === null ? null : (
                          <a
                            key={row.id}
                            className="strategy-control-marker"
                            style={{
                              left: `${position}%`,
                              top: `${(lane % 2) * 20}px`,
                            }}
                            href={`#control-${row.id}`}
                            aria-label={`Race control ${index + 1}, ${count} source messages on lap ${row.lap_number}: ${row.message}`}
                          >
                            RC{index + 1}
                            {count > 1 ? "+" : ""}
                          </a>
                        );
                      },
                    )}
                  </div>
                </div>
              )}
              {selected.map((row, index) => {
                const lanes = stintLanes(
                  row.stints.map((stint) => stint.source),
                );
                return (
                  <div className="strategy-timeline-row" key={strategyKey(row)}>
                    <div className="strategy-row-label">
                      {index === 0 ? "A" : "B"} · {name(row)}
                      <span className="cell-detail">
                        {row.provider} · {row.recorded_lap_count} recorded laps
                      </span>
                    </div>
                    <div
                      className="strategy-track"
                      style={{
                        height: `${32 + (Math.max(0, ...lanes.map((lane) => lane ?? 0)) + 1) * 44}px`,
                      }}
                    >
                      {row.stints.map((stint, stintIndex) => {
                        const s = stint.source,
                          span = stintSpan(s.lap_start, s.lap_end, axis);
                        return span === null ? null : (
                          <a
                            key={s.id}
                            className={`strategy-stint ${compoundClass(s.compound)}`}
                            style={{
                              left: `${span.left}%`,
                              width: `${span.width}%`,
                              top: `${28 + (lanes[stintIndex] ?? 0) * 44}px`,
                            }}
                            href={`#stint-${s.id}`}
                            aria-label={`${name(row)}, stint ${s.stint_number}, ${s.compound ?? "compound unavailable"}, source laps ${s.lap_start} to ${s.lap_end}${stint.context_status !== "available" ? ", ambiguous context" : ""}`}
                          >
                            <span>
                              {s.stint_number} · {s.compound ?? "Unavailable"}
                            </span>
                          </a>
                        );
                      })}
                      {row.pits.map((pit) => {
                        const position = lapPosition(pit.lap_number, axis);
                        return position === null ? null : (
                          <a
                            key={pit.id}
                            className="strategy-pit-marker"
                            style={{ left: `${position}%` }}
                            href={`#pit-${pit.id}`}
                            aria-label={`${name(row)}, pit stop on source lap ${pit.lap_number}`}
                          >
                            <span>P</span>
                          </a>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
              <div className="strategy-timeline-row">
                <div className="strategy-row-label">Recorded laps</div>
                <div className="strategy-axis">
                  <span>1</span>
                  <span>{Math.ceil(axis / 2)}</span>
                  <span>{axis}</span>
                </div>
              </div>
            </div>
          </div>
        )}
        <p className="section-note">
          P = source pit stop; RC = recorded safety-car/VSC message. A + groups
          multiple messages on the same source lap. Details below provide text
          alternatives, including records with unavailable lap numbers.
          Overlapping source stints occupy separate lanes; shared laps are
          excluded from calculated pace.
        </p>
      </section>
      <section aria-label="Stint ages and observed pace">
        <SectionHeading title="Stint detail" />
        <p className="section-note">
          Source: compound, boundaries and age when fitted. Calculated:
          completed stint laps, total tyre age and observed pace. Total age uses
          source starting age + completed stint laps (
          {selected[0]?.stints[0]?.age_formula_version ?? "completed-laps-v1"});
          an unknown starting age stays unavailable. Ages are after the reported
          snapshot lap: the source end lap for unambiguous bounds, or the last
          uniquely contained timed lap when bounds overlap. This is not always
          final age.
        </p>
        <p className="section-note">
          Observed pace uses positive-duration laps confirmed as non-pit-out,
          excluding source pit laps, the following lap and shared stint-boundary
          laps. A missing pit lap disables pace. Average and best lap include
          traffic and neutralisations; they are not clean-air pace or evidence
          of team intent. Missing records are never filled.
        </p>
        {selected.map((row, index) => (
          <div className="strategy-driver-detail" key={strategyKey(row)}>
            <h3>
              {index === 0 ? "A" : "B"} · {name(row)}{" "}
              <span className="muted">{row.provider}</span>
            </h3>
            {!row.stints.length ? (
              <p className="section-note">
                No source stints have been imported for this driver.
              </p>
            ) : (
              <TableRegion
                label={`${name(row)} source stints and calculated pace`}
              >
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Stint / compound</th>
                      <th scope="col">Source laps</th>
                      <th scope="col" className="numeric">
                        Age when fitted
                      </th>
                      <th scope="col" className="numeric">
                        Stint usage / snapshot lap
                      </th>
                      <th scope="col" className="numeric">
                        Total age at snapshot
                      </th>
                      <th scope="col" className="numeric">
                        Average pace
                      </th>
                      <th scope="col" className="numeric">
                        Best lap
                      </th>
                      <th scope="col">Pace coverage</th>
                    </tr>
                  </thead>
                  <tbody>
                    {row.stints.map((stint) => (
                      <tr
                        key={stint.source.id}
                        id={`stint-${stint.source.id}`}
                        tabIndex={-1}
                      >
                        <th scope="row">
                          {stint.source.stint_number} ·{" "}
                          {stint.source.compound ?? "Unavailable"}
                          <span className="cell-detail">
                            {contextNote(stint)}
                          </span>
                        </th>
                        <td>
                          {stint.source.lap_start ?? "Unavailable"}–
                          {stint.source.lap_end ?? "Unavailable"}
                        </td>
                        <td className="numeric">
                          {stint.source.tyre_age_at_start ?? "Unavailable"}
                        </td>
                        <td className="numeric">
                          {stint.completed_laps_on_stint ?? "Unavailable"}
                          <span className="cell-detail">
                            After lap {stint.age_completed_lap ?? "Unavailable"}
                          </span>
                        </td>
                        <td className="numeric">
                          {stint.total_tyre_age ?? "Unavailable"}
                        </td>
                        <td className="numeric">
                          {paceTime(stint.pace.average_seconds)}
                        </td>
                        <td className="numeric">
                          {paceTime(stint.pace.best_seconds)}
                        </td>
                        <td>
                          {stint.pace.included_laps} included /{" "}
                          {stint.pace.excluded_laps} excluded
                          <span className="cell-detail">
                            {stint.pace.recorded_laps} recorded within source
                            bounds
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableRegion>
            )}
          </div>
        ))}
      </section>
      <section aria-label="Source pit stops">
        <SectionHeading title="Pit stops" />
        <p className="section-note">
          Source data. Pit-lane duration and stationary stop duration are
          separate measurements. Timestamps are UTC; missing lap or duration
          stays unavailable.
        </p>
        {!selected.some((row) => row.pits.length) ? (
          <EmptyState title="No imported pit records">
            <p>
              No pit stops are recorded for these drivers. This does not
              establish that no stops occurred.
            </p>
          </EmptyState>
        ) : (
          <TableRegion label="Compared driver pit stops">
            <table>
              <thead>
                <tr>
                  <th scope="col">Driver / provider</th>
                  <th scope="col">Source lap</th>
                  <th scope="col">Timestamp (UTC)</th>
                  <th scope="col" className="numeric">
                    Pit lane
                  </th>
                  <th scope="col" className="numeric">
                    Stationary stop
                  </th>
                </tr>
              </thead>
              <tbody>
                {selected.flatMap((row) =>
                  row.pits.map((pit) => (
                    <tr key={pit.id} id={`pit-${pit.id}`} tabIndex={-1}>
                      <th scope="row">
                        {name(row)}
                        <span className="cell-detail">{row.provider}</span>
                      </th>
                      <td>{pit.lap_number ?? "Unavailable"}</td>
                      <td>
                        <time dateTime={pit.timestamp}>
                          {formatSchedule({
                            starts_at: pit.timestamp,
                            scheduled_date: null,
                          })}
                        </time>
                      </td>
                      <td className="numeric">
                        {seconds(pit.lane_duration_seconds)}
                      </td>
                      <td className="numeric">
                        {seconds(pit.stop_duration_seconds)}
                      </td>
                    </tr>
                  )),
                )}
              </tbody>
            </table>
          </TableRegion>
        )}
      </section>
      <section aria-label="Recorded safety-car and VSC context">
        <SectionHeading title="Safety-car / VSC context" />
        <p className="section-note">
          Source race-control messages, scoped to the selected providers/drivers
          and session-wide messages. These records do not establish complete
          deployment periods, green-flag coverage or a reason for a pit stop.
        </p>
        {!controls.length ? (
          <EmptyState title="Context unavailable">
            <p>
              No safety-car/VSC messages have been imported for this selection.
              Absence of records does not establish an uninterrupted race.
            </p>
          </EmptyState>
        ) : (
          <ol className="strategy-control-list">
            {controls.map((row, index) => (
              <li key={row.id} id={`control-${row.id}`} tabIndex={-1}>
                <div>
                  <strong>
                    RC{index + 1} ·{" "}
                    {row.lap_number === null
                      ? "Lap unavailable"
                      : `Lap ${row.lap_number}`}
                  </strong>
                  <span className="cell-detail">
                    <time dateTime={row.timestamp}>
                      {formatSchedule({
                        starts_at: row.timestamp,
                        scheduled_date: null,
                      })}
                    </time>{" "}
                    · {row.provider} ·{" "}
                    {row.driver_id
                      ? driverName(drivers.get(row.driver_id)!)
                      : "Session-wide"}
                  </span>
                </div>
                <p>{row.message}</p>
              </li>
            ))}
          </ol>
        )}
      </section>
    </>
  );
}

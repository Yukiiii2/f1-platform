import type { Driver } from "../_lib/contracts";
import type { Comparison, Lap, TyreContext } from "../_lib/telemetry-contracts";
import { driverName, formatDuration } from "../_lib/format";
import { channelNumber, signedDelta } from "../_lib/telemetry";
import { EmptyState, SectionHeading, TableRegion } from "../_components/ui";
import { TraceCharts } from "./trace-charts";

const warningText: Record<string, string> = {
  approximate_lap_window:
    "Samples were selected using an estimated lap window.",
  approximate_start_requires_opt_in:
    "The lap start is approximate. Enable estimated lap windows to include its telemetry.",
  lap_time_or_start_unavailable:
    "Source lap timing or start is unavailable; its telemetry cannot be aligned.",
  no_eligible_samples: "No eligible telemetry samples are stored for this lap.",
  lap_duration_unavailable_or_nonpositive:
    "A usable lap duration is unavailable; traces cannot be aligned.",
  samples_unavailable: "No eligible samples are available for either lap.",
  incomplete_speed_coverage_elapsed_time_fallback:
    "Speed coverage is incomplete or has zero integrated distance. The API returned elapsed-time alignment without a delta trace.",
  missing_channels_or_sample_gaps:
    "Some channels or samples are missing. Chart gaps and unavailable values are preserved.",
};
function readableWarning(warning: string): string {
  const parts = warning.split(":");
  const key = parts.at(-1)!;
  const prefix = parts.length > 1 ? `Lap ${parts[0].toUpperCase()}: ` : "";
  return (
    prefix +
    (warningText[key] ??
      "Additional telemetry limitations were reported by the API.")
  );
}
function lapTime(value: string | null) {
  const number = channelNumber(value);
  return number === null
    ? "Unavailable"
    : formatDuration(Math.round(number * 1000));
}
function sectorTime(value: string | null) {
  const number = channelNumber(value);
  return number === null ? "Unavailable" : `${number.toFixed(3)} s`;
}
function tyreDetails(tyres: TyreContext, label: string) {
  return (
    <div>
      <h3>{label}</h3>
      {tyres.status !== "available" ? (
        <p className="section-note">
          {tyres.status === "ambiguous"
            ? "Overlapping stints make tyre context ambiguous."
            : "A complete source stint is unavailable for this lap."}{" "}
          Compound and age are unavailable.
        </p>
      ) : (
        <>
          <dl className="tyre-facts">
            <div>
              <dt>Compound · source</dt>
              <dd>{tyres.compound ?? "Unavailable"}</dd>
            </div>
            <div>
              <dt>Stint laps · source</dt>
              <dd>
                {tyres.lap_start}–{tyres.lap_end}
              </dd>
            </div>
            <div>
              <dt>Age at stint start · source</dt>
              <dd>{tyres.tyre_age_at_start ?? "Unavailable"}</dd>
            </div>
            <div>
              <dt>Stint laps completed · calculated</dt>
              <dd>
                {tyres.completed_laps_before ?? "Unavailable"} before /{" "}
                {tyres.completed_laps_after ?? "Unavailable"} after
              </dd>
            </div>
            <div>
              <dt>Total tyre age · calculated</dt>
              <dd>
                {tyres.total_age_before ?? "Unavailable"} before /{" "}
                {tyres.total_age_after ?? "Unavailable"} after
              </dd>
            </div>
          </dl>
          {tyres.tyre_age_at_start === null && (
            <p className="section-note">
              Starting tyre age was not supplied. Total age remains unavailable.
            </p>
          )}
        </>
      )}
    </div>
  );
}

export function ComparisonView({
  comparison,
  drivers,
}: {
  comparison: Comparison;
  drivers: Map<string, Driver>;
}) {
  const { lap_a: a, lap_b: b, trace } = comparison;
  function name(lap: Lap) {
    const driver = drivers.get(lap.driver_id);
    return `${driver ? driverName(driver) : "Driver unavailable"} · Lap ${lap.lap_number}`;
  }
  const labelA = name(a.lap),
    labelB = name(b.lap);
  const delta = channelNumber(comparison.lap_delta_ms);
  return (
    <>
      <SectionHeading title="Lap comparison" />
      <p className="comparison-legend">
        <span className="legend-a">A · {labelA}</span>
        <span className="legend-b">B · {labelB}</span>
      </p>
      <p className="section-note">
        Source timing. Calculated deltas use A − B: positive means A took
        longer; negative means A was faster.
      </p>
      <TableRegion label="Source lap and sector timing comparison">
        <table>
          <thead>
            <tr>
              <th scope="col">Timing</th>
              <th scope="col" className="numeric">
                Lap A
              </th>
              <th scope="col" className="numeric">
                Lap B
              </th>
              <th scope="col" className="numeric">
                A − B
              </th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">Lap time</th>
              <td className="numeric">{lapTime(a.lap.duration_seconds)}</td>
              <td className="numeric">{lapTime(b.lap.duration_seconds)}</td>
              <td className="numeric">
                {signedDelta(comparison.lap_delta_ms)}
                {delta !== null && (
                  <span className="cell-detail">
                    {delta < 0
                      ? "A faster"
                      : delta > 0
                        ? "A slower"
                        : "Equal times"}
                  </span>
                )}
              </td>
            </tr>
            {([1, 2, 3] as const).map((index) => (
              <tr key={index}>
                <th scope="row">Sector {index}</th>
                <td className="numeric">
                  {sectorTime(a.lap[`sector_${index}_seconds`])}
                </td>
                <td className="numeric">
                  {sectorTime(b.lap[`sector_${index}_seconds`])}
                </td>
                <td className="numeric">
                  {signedDelta(comparison.sector_delta_ms[`sector_${index}`])}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableRegion>
      <section aria-label="Selected lap tyre context">
        <SectionHeading title="Tyre context" />
        <div className="tyre-context">
          {tyreDetails(a.tyres, `A · ${labelA}`)}
          {tyreDetails(b.tyres, `B · ${labelB}`)}
        </div>
        <p className="section-note">
          Ages are completed laps, calculated from source stint metadata using{" "}
          {a.tyres.formula_version}. Unknown starting ages are not treated as
          fresh tyres.
        </p>
      </section>
      <section aria-label="Synchronized telemetry traces">
        <SectionHeading title="Synchronized traces" />
        <p
          className={`trace-provenance ${trace.classification === "estimate" ? "trace-estimate" : ""}`}
        >
          <strong>
            {trace.classification === "estimate" ? "Estimate" : "Calculated"}
          </strong>
          {" · "}
          {trace.classification === "estimate"
            ? "Approximate lap windows. These traces are not official lap-position telemetry."
            : "Resampled stored telemetry. Raw source samples remain unchanged."}
        </p>
        <p className="section-note">
          {trace.alignment === "normalized_distance"
            ? "Axis: fraction of independently integrated lap distance, not GPS or authoritative track position."
            : trace.alignment === "elapsed_time"
              ? "Axis: elapsed seconds from each lap start. Equal elapsed time does not establish equal track position."
              : "Alignment is unavailable for these laps."}{" "}
          A: {trace.sample_count_a} eligible samples ({a.lap.provider}); B:{" "}
          {trace.sample_count_b} ({b.lap.provider}). Continuous channels use
          linear interpolation; state channels hold the previous sample. Gaps
          over {trace.max_interpolation_gap_seconds} second are not bridged.
        </p>
        {trace.warnings.length > 0 && (
          <ul className="trace-warnings">
            {[...new Set(trace.warnings)].map((warning) => (
              <li key={warning}>{readableWarning(warning)}</li>
            ))}
          </ul>
        )}
        {trace.availability === "unavailable" || !trace.points.length ? (
          <EmptyState title="Telemetry unavailable">
            <p>
              Lap and sector timing above remains usable where supplied. Choose
              other laps or enable estimated windows if the source lap starts
              are approximate.
            </p>
          </EmptyState>
        ) : (
          <TraceCharts trace={trace} labelA={labelA} labelB={labelB} />
        )}
      </section>
    </>
  );
}

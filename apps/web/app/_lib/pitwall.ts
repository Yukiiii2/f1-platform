import type {
  Evidence,
  GroundedValue,
  Json,
  PageContext,
  QueryRequest,
} from "./pitwall-contracts";
import type { Comparison } from "./telemetry-contracts";
import type { DriverStrategy } from "./strategy-contracts";

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function pageContext(input: object): PageContext {
  const data = input as Record<string, unknown>;
  const result: PageContext = {};
  if (data.route !== undefined) {
    if (typeof data.route !== "string" || data.route.length > 300)
      throw new Error("Invalid context");
    result.route = data.route;
  }
  for (const key of [
    "event_id",
    "session_id",
    "driver_id",
    "lap_id",
    "stint_id",
  ] as const) {
    if (data[key] !== undefined) {
      if (typeof data[key] !== "string" || !uuid.test(data[key]))
        throw new Error("Invalid context");
      result[key] = data[key];
    }
  }
  if (data.season !== undefined) {
    if (
      typeof data.season !== "number" ||
      !Number.isInteger(data.season) ||
      data.season < 1950 ||
      data.season > 2100
    )
      throw new Error("Invalid context");
    result.season = data.season;
  }
  if (
    data.allow_approximate !== undefined &&
    typeof data.allow_approximate !== "boolean"
  )
    throw new Error("Invalid context");
  if (data.comparison !== undefined) {
    if (!data.comparison || typeof data.comparison !== "object")
      throw new Error("Invalid comparison");
    const comparison = data.comparison as Record<string, unknown>;
    const count = comparison.sample_count ?? 201;
    const alignment = comparison.alignment ?? "normalized_distance";
    if (
      typeof comparison.lap_a_id !== "string" ||
      !uuid.test(comparison.lap_a_id) ||
      typeof comparison.lap_b_id !== "string" ||
      !uuid.test(comparison.lap_b_id) ||
      comparison.lap_a_id === comparison.lap_b_id ||
      typeof count !== "number" ||
      !Number.isInteger(count) ||
      count < 2 ||
      count > 201 ||
      (alignment !== "normalized_distance" && alignment !== "elapsed_time") ||
      (comparison.allow_approximate !== undefined &&
        typeof comparison.allow_approximate !== "boolean")
    )
      throw new Error("Invalid comparison");
    result.comparison = {
      lap_a_id: comparison.lap_a_id,
      lap_b_id: comparison.lap_b_id,
      sample_count: count,
      alignment,
      allow_approximate: comparison.allow_approximate === true,
    };
  }
  result.allow_approximate =
    data.allow_approximate === true ||
    result.comparison?.allow_approximate === true;
  return result;
}
export function queryRequest(question: string, context: object): QueryRequest {
  if (
    typeof question !== "string" ||
    !question.trim() ||
    question.trim().length > 4000
  )
    throw new Error("Invalid question");
  return { question: question.trim(), context: pageContext(context) };
}
export function pitwallError(status: number): string {
  if (status === 429)
    return "Pitwall is temporarily unavailable because it is busy. Your question is still here; try again shortly.";
  if (status === 422 || status === 404)
    return "This question or page context could not be used. Refresh your selection or narrow the question, then ask again.";
  if (status === 502)
    return "Pitwall could not support an answer with the available evidence. Try a more specific question.";
  return "Pitwall is temporarily unavailable. Your question is still here; please try again later.";
}

type SuggestionContext =
  | { page: "race"; hasSession: boolean; hasResults: boolean }
  | {
      page: "driver";
      hasWeekend: boolean;
      hasResults: boolean;
      hasSeason: boolean;
      hasStanding: boolean;
    }
  | { page: "telemetry"; hasLaps: boolean; comparison: Comparison | null }
  | {
      page: "strategy";
      drivers: (Pick<DriverStrategy, "stints" | "pits"> & { name: string })[];
    };

// Suggestions use only records already loaded by the page. Unknown coverage is
// phrased as a question, never as a claim that telemetry or timing exists.
export function suggestedQuestions(context: SuggestionContext): string[] {
  if (context.page === "race")
    return [
      context.hasSession
        ? context.hasResults
          ? "What do the recorded results show for this session?"
          : "Which session results are unavailable for this weekend?"
        : "Which session records, if any, are available for this weekend?",
      context.hasSession
        ? "Are weather and race-control records available for this session? State missing data."
        : "Which weekend data are unavailable for analysis?",
    ];
  if (context.page === "driver") {
    const questions = [
      context.hasWeekend
        ? context.hasResults
          ? "What do the recorded results show for this driver in the selected weekend?"
          : "Which results are unavailable for this driver in the selected weekend?"
        : "What recorded profile information is available for this driver?",
    ];
    if (context.hasSeason)
      questions.push(
        context.hasStanding
          ? "What do the recorded championship standings show for this driver?"
          : "Are championship standings available for this driver in the selected season?",
      );
    else questions.push("Which season data are unavailable for this driver?");
    return questions;
  }
  if (context.page === "telemetry") {
    if (!context.hasLaps)
      return [
        "Which lap and telemetry data are unavailable for this session?",
        "What session records, if any, are available without lap telemetry?",
      ];
    const questions: string[] = [];
    const comparison = context.comparison;
    const lapDelta = comparison && comparison.lap_delta_ms !== null;
    const sectorDeltas =
      comparison &&
      Object.values(comparison.sector_delta_ms).some((value) => value !== null);
    if (lapDelta || sectorDeltas)
      questions.push(
        `What do the calculated ${lapDelta && sectorDeltas ? "lap and sector deltas" : lapDelta ? "lap delta" : "sector deltas"} show for A versus B?`,
      );
    if (
      comparison?.trace.points.some((point) =>
        [
          ...Object.values(point.channels_a),
          ...Object.values(point.channels_b),
        ].some((value) => value !== null),
      )
    )
      questions.push(
        "Compare the available telemetry for these laps. Keep estimates separate and state missing channels.",
      );
    if (!comparison)
      questions.push(
        "Which recorded laps are available for comparison in this session?",
      );
    questions.push(
      comparison
        ? "Which timing, tyre or telemetry values are unavailable for the selected laps?"
        : "Which telemetry channels, if any, are available for this session, and which are missing?",
    );
    return questions;
  }
  const names = context.drivers.map((row) => row.name).join(" and ");
  const questions: string[] = [];
  if (context.drivers.some((row) => row.stints.length)) {
    const pace = context.drivers.some((row) =>
      row.stints.some((stint) => stint.pace.average_seconds !== null),
    );
    questions.push(
      `${context.drivers.length > 1 ? "Compare" : "Summarize"} recorded stints and available starting tyre ages${pace ? ", with available observed non-pit pace" : ""} for ${names}. Keep interpretation separate.`,
    );
  }
  if (context.drivers.some((row) => row.pits.length))
    questions.push(`What do the recorded pit stops show for ${names}?`);
  questions.push(
    "Which stint, tyre-age, pit or pace data are unavailable for this race?",
  );
  return questions;
}
const titles: Record<string, string> = {
  get_drivers: "Driver directory",
  get_driver: "Driver profile",
  get_events: "Race weekends",
  get_event: "Race weekend",
  get_sessions: "Weekend sessions",
  get_session: "Session",
  get_results: "Session results",
  get_laps: "Recorded laps",
  get_lap: "Recorded lap",
  get_telemetry: "Recorded telemetry",
  get_lap_telemetry: "Lap telemetry",
  get_stints: "Recorded stints",
  get_stint: "Recorded stint",
  get_stint_age: "Tyre age",
  get_pits: "Pit stops",
  get_positions: "Race positions",
  get_intervals: "Race intervals",
  get_standings: "Championship standings",
  get_race_control: "Race control",
  get_weather: "Weather",
  get_strategy: "Stints and observed pace",
  compare_laps: "Lap comparison",
};
export function evidenceTitle(tool: string): string {
  return titles[tool] ?? "Recorded data";
}
const labels: Record<string, string> = {
  tyre_age_at_start: "Tyre age when fitted",
  total_tyre_age: "Total tyre age",
  total_age_before: "Tyre age before lap",
  total_age_after: "Tyre age after lap",
  lap_start: "First stint lap",
  lap_end: "Last stint lap",
  age_completed_lap: "Tyre-age snapshot lap",
  completed_laps_on_stint: "Completed stint laps",
  lap_delta_ms: "Lap delta (A − B)",
  delta_ms: "Delta (A − B)",
  sector_1_delta_ms: "Sector 1 delta (A − B)",
  sector_2_delta_ms: "Sector 2 delta (A − B)",
  sector_3_delta_ms: "Sector 3 delta (A − B)",
  average_seconds: "Observed average pace",
  best_seconds: "Best eligible lap",
  duration_seconds: "Lap time",
  sector_1_seconds: "Sector 1 time",
  sector_2_seconds: "Sector 2 time",
  sector_3_seconds: "Sector 3 time",
  rpm: "RPM",
  drs_state: "DRS",
  brake_applied: "Brake state",
  speed_kph: "Speed",
  throttle_percent: "Throttle",
  starts_at: "Start time",
  ends_at: "End time",
  lane_duration_seconds: "Pit-lane duration",
  stop_duration_seconds: "Stationary stop duration",
};
export function fieldLabel(key: string): string {
  return (
    labels[key] ??
    key.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase())
  );
}
export function valueField(pointer: string): string {
  const key = pointer.split("/").at(-1) ?? "Value";
  return pointer.includes("/sector_delta_ms/") ? `${key}_delta_ms` : key;
}
export function displayValue(row: GroundedValue): boolean {
  // Retrieval metadata is not an answer. Never surface provider/configuration fields.
  return !row.pointer
    .split("/")
    .some((key) =>
      /^(provider|updates|session_status|live_.*|data_status|id|.*_id|.*version|classification|policy|api_key|model|prompt|source_revision.*|raw.*)$/.test(
        key,
      ),
    );
}
export function formatValue(key: string, value: Json): string {
  if (value === null || typeof value === "object") return "Unavailable";
  if (key === "brake_applied" && typeof value === "boolean")
    return value ? "Applied" : "Released";
  if (key === "drs_state") return `Code ${value}`;
  if (typeof value === "boolean") return value ? "Yes" : "No";
  const text = String(value);
  if (key.endsWith("delta_ms") && Number.isFinite(Number(value)))
    return `${Number(value) > 0 ? "+" : ""}${text} ms`;
  if (key.endsWith("_ms")) return `${text} ms`;
  if (key.endsWith("_seconds")) return `${text} s`;
  if (key === "speed_kph") return `${text} km/h`;
  if (key.endsWith("_percent")) return `${text}%`;
  if (
    [
      "tyre_age_at_start",
      "total_tyre_age",
      "total_age_before",
      "total_age_after",
      "completed_laps_on_stint",
      "completed_laps_before",
      "completed_laps_after",
    ].includes(key)
  )
    return `${text} laps`;
  return text;
}
function record(value: Json | undefined): Record<string, Json> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value
    : null;
}
export function valueLabel(
  row: Pick<GroundedValue, "pointer" | "evidence_id">,
  evidence: Evidence[],
  names: Record<string, string>,
): string {
  const source = evidence.find((item) => item.id === row.evidence_id);
  const parts = row.pointer
    .split("/")
    .slice(1)
    .map((part) => part.replaceAll("~1", "/").replaceAll("~0", "~"));
  let node: Json | undefined = source?.data;
  let driver: string | undefined;
  let lap: Json | undefined;
  let stint: Json | undefined;
  let stintId: Json | undefined;
  let timestamp: Json | undefined;
  let coordinate: Json | undefined;
  for (const part of parts.slice(0, -1)) {
    node = Array.isArray(node) ? node[Number(part)] : record(node)?.[part];
    const object = record(node);
    if (typeof object?.driver_id === "string") driver = object.driver_id;
    if (object?.lap_number !== undefined) lap = object.lap_number;
    if (object?.stint_number !== undefined) stint = object.stint_number;
    if (object?.stint_id !== undefined) stintId = object.stint_id;
    if (object?.timestamp !== undefined) timestamp = object.timestamp;
    if (object?.coordinate !== undefined) coordinate = object.coordinate;
  }
  const side =
    parts.includes("lap_a") ||
    parts.includes("channels_a") ||
    parts.at(-1) === "elapsed_seconds_a"
      ? "a"
      : parts.includes("lap_b") ||
          parts.includes("channels_b") ||
          parts.at(-1) === "elapsed_seconds_b"
        ? "b"
        : null;
  if (side) {
    const selectedLap = record(
      record(record(source?.data.source)?.[`lap_${side}`])?.lap,
    );
    if (!driver && typeof selectedLap?.driver_id === "string")
      driver = selectedLap.driver_id;
    if (lap === undefined && selectedLap?.lap_number !== undefined)
      lap = selectedLap.lap_number;
  }
  if (!driver && typeof source?.arguments.driver_id === "string")
    driver = source.arguments.driver_id;
  if (stintId && stint === undefined) {
    const drivers = record(source?.data.source)?.drivers;
    if (Array.isArray(drivers))
      for (const item of drivers) {
        const stints = record(item)?.stints;
        if (Array.isArray(stints)) {
          const found = stints.map(record).find((item) => item?.id === stintId);
          if (found) stint = found.stint_number;
        }
      }
  }
  const context = [
    side ? `Lap ${side.toUpperCase()}` : null,
    driver ? (names[driver] ?? "Driver record") : null,
    lap !== undefined && lap !== null ? `Lap ${lap}` : null,
    stint !== undefined && stint !== null ? `Stint ${stint}` : null,
    timestamp !== undefined && timestamp !== null ? `At ${timestamp}` : null,
    coordinate !== undefined && coordinate !== null
      ? (() => {
          const trace = record(record(source?.data[parts[0]])?.trace);
          return trace?.axis === "elapsed_seconds"
            ? `Elapsed ${coordinate} s`
            : trace?.axis === "fraction_of_integrated_distance"
              ? `Integrated distance fraction ${coordinate}`
              : `Comparison coordinate ${coordinate}`;
        })()
      : null,
  ];
  return [...context.filter(Boolean), fieldLabel(valueField(row.pointer))].join(
    " · ",
  );
}
export function unavailableLabel(
  message: string,
  evidence: Evidence[],
  names: Record<string, string>,
): string {
  const match = /^(e\d+)(\/(?:source|derived|estimate)\/[^:]+):/.exec(message);
  if (match)
    return `${valueLabel({ evidence_id: match[1], pointer: match[2] }, evidence, names)}: unavailable in recorded data.`;
  const id = /^(e\d+):/.exec(message)?.[1];
  const row = evidence.find((item) => item.id === id);
  const title = row ? evidenceTitle(row.tool) : "Recorded data";
  if (message.includes("partial page"))
    return `${title}: partial records; complete coverage is unavailable in this answer.`;
  if (message.includes("nulls remain unknown"))
    return `${title}: some values are unavailable and remain unknown.`;
  if (message.includes("team-only/unsupported"))
    return "This channel or team-only information is unavailable in the public race data.";
  if (row?.error === "approximate_opt_in_required")
    return `${title}: estimated lap windows need your permission. Enable them in the Telemetry Lab and compare again.`;
  if (row?.error === "result_too_large_use_narrower_query")
    return `${title}: too many records for this answer. Ask about a specific driver or lap.`;
  return `${title}: insufficient data for this question. Try a specific session, driver or lap.`;
}

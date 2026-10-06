export function strategyKey(row: { driver_id: string; provider: string }) {
  return `${row.provider}:${row.driver_id}`;
}

export function selectStrategies<
  T extends { driver_id: string; provider: string },
>(drivers: T[], params: { a?: string; b?: string }): T[] | null {
  if (!drivers.length) return [];
  const a =
    params.a === undefined
      ? drivers[0]
      : drivers.find((row) => strategyKey(row) === params.a);
  const b =
    params.b === undefined
      ? drivers.find((row) => row !== a)
      : params.b === ""
        ? undefined
        : drivers.find((row) => strategyKey(row) === params.b);
  if (!a || (params.b && !b) || a === b) return null;
  return b ? [a, b] : [a];
}

// Display geometry only: inclusive source lap bins, never time-to-lap inference.
export function stintSpan(
  first: number | null,
  last: number | null,
  axis: number | null,
) {
  if (
    first === null ||
    last === null ||
    axis === null ||
    axis < 1 ||
    first < 1 ||
    last < first ||
    last > axis
  )
    return null;
  return {
    left: ((first - 1) / axis) * 100,
    width: ((last - first + 1) / axis) * 100,
  };
}
export function lapPosition(lap: number | null, axis: number | null) {
  if (lap === null || axis === null || axis < 1 || lap < 1 || lap > axis)
    return null;
  return ((lap - 0.5) / axis) * 100;
}

export function stintLanes(
  stints: { lap_start: number | null; lap_end: number | null }[],
) {
  const ends: number[] = [];
  return stints.map(({ lap_start: first, lap_end: last }) => {
    if (first === null || last === null || last < first) return null;
    let lane = ends.findIndex((end) => end < first);
    if (lane === -1) lane = ends.length;
    ends[lane] = last;
    return lane;
  });
}

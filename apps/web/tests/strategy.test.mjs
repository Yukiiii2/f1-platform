import assert from "node:assert/strict";
import { test } from "node:test";
import {
  selectStrategies,
  stintLanes,
  stintSpan,
  lapPosition,
} from "../app/_lib/strategy.ts";

test("overlapping source spans occupy separate lanes and remain unchanged", () => {
  const stints = [
    { lap_start: 1, lap_end: 3 },
    { lap_start: 3, lap_end: 4 },
    { lap_start: 4, lap_end: 8 },
    { lap_start: null, lap_end: 9 },
  ];
  const before = structuredClone(stints);
  assert.deepEqual(stintLanes(stints), [0, 1, 0, null]);
  assert.deepEqual(stints, before);
});

test("timeline spans use inclusive source lap bins without guessing missing boundaries", () => {
  assert.deepEqual(stintSpan(4, 8, 10), { left: 30, width: 50 });
  assert.deepEqual(stintSpan(1, 1, 10), { left: 0, width: 10 });
  assert.deepEqual(stintSpan(10, 10, 10), { left: 90, width: 10 });
  assert.equal(stintSpan(null, 8, 10), null);
  assert.equal(stintSpan(4, null, 10), null);
  assert.equal(stintSpan(8, 4, 10), null);
  assert.equal(stintSpan(4, 8, null), null);
  assert.equal(lapPosition(5, 10), 45);
  assert.equal(lapPosition(null, 10), null);
});

test("driver comparisons use distinct provider-scoped records and reject stale selections", () => {
  const drivers = [
    { driver_id: "a", provider: "openf1" },
    { driver_id: "b", provider: "openf1" },
    { driver_id: "a", provider: "other" },
  ];
  assert.deepEqual(selectStrategies(drivers, {}), drivers.slice(0, 2));
  assert.deepEqual(selectStrategies(drivers, { a: "openf1:a", b: "other:a" }), [
    drivers[0],
    drivers[2],
  ]);
  assert.deepEqual(selectStrategies(drivers, { a: "openf1:a", b: "" }), [
    drivers[0],
  ]);
  assert.equal(
    selectStrategies(drivers, { a: "openf1:a", b: "openf1:a" }),
    null,
  );
  assert.equal(selectStrategies(drivers, { a: "missing:a" }), null);
  assert.deepEqual(selectStrategies([drivers[0]], {}), [drivers[0]]);
  assert.deepEqual(selectStrategies([], {}), []);
});

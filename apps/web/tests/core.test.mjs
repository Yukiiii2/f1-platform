import assert from "node:assert/strict";
import { createServer } from "node:http";
import { test } from "node:test";
import { ApiError, getList, getEntity } from "../app/_lib/api.ts";
import {
  formatPoints,
  formatSchedule,
  formatDuration,
  selectSeason,
} from "../app/_lib/format.ts";

async function withApi(handler, run) {
  const server = createServer(handler);
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const previous = process.env.NEXT_PUBLIC_API_URL;
  process.env.NEXT_PUBLIC_API_URL = `http://127.0.0.1:${server.address().port}`;
  try {
    await run();
  } finally {
    if (previous === undefined) delete process.env.NEXT_PUBLIC_API_URL;
    else process.env.NEXT_PUBLIC_API_URL = previous;
    await new Promise((resolve) => server.close(resolve));
  }
}

test("reads every page and preserves season filters", async () => {
  const urls = [];
  await withApi(
    (request, response) => {
      const url = new URL(request.url, "http://test");
      urls.push(url);
      const offset = Number(url.searchParams.get("offset"));
      response.setHeader("Content-Type", "application/json");
      response.end(
        JSON.stringify(
          Array.from({ length: offset === 0 ? 200 : 1 }, (_, index) => ({
            id: String(offset + index),
          })),
        ),
      );
    },
    async () => {
      const rows = await getList("events", { season: 2025 });
      assert.equal(rows.length, 201);
      assert.deepEqual(
        urls.map((url) => url.searchParams.get("offset")),
        ["0", "200"],
      );
      assert.ok(
        urls.every(
          (url) =>
            url.pathname === "/v1/events" &&
            url.searchParams.get("season") === "2025",
        ),
      );
    },
  );
});

test("distinguishes missing records from unavailable data", async () => {
  await withApi(
    (request, response) => {
      response.writeHead(404);
      response.end();
    },
    async () => {
      await assert.rejects(
        getEntity("drivers", "00000000-0000-0000-0000-000000000001"),
        (error) => error instanceof ApiError && error.status === 404,
      );
    },
  );
  await withApi(
    (request, response) => {
      response.writeHead(503);
      response.end("private server details");
    },
    async () => {
      await assert.rejects(
        getList("seasons"),
        (error) =>
          error instanceof ApiError &&
          error.status === 503 &&
          !error.message.includes("private"),
      );
    },
  );
});

test("rejects provider envelopes and repeated pages rather than showing partial data", async () => {
  await withApi(
    (request, response) => {
      response.end(JSON.stringify({ MRData: {} }));
    },
    async () => {
      await assert.rejects(getList("drivers"), ApiError);
    },
  );
  await withApi(
    (request, response) => {
      response.end(
        JSON.stringify(
          Array.from({ length: 200 }, (_, index) => ({ id: String(index) })),
        ),
      );
    },
    async () => {
      await assert.rejects(getList("drivers"), ApiError);
    },
  );
});

test("keeps missing and fractional source values distinct from zero", () => {
  assert.equal(formatPoints(null), "Not available");
  assert.equal(formatPoints("0.000"), "0");
  assert.equal(formatPoints("24.500"), "24.5");
  assert.equal(formatDuration(null), "Not available");
  assert.equal(formatDuration(6126304), "1:42:06.304");
});

test("date-only schedules never invent a start time", () => {
  const label = formatSchedule({
    scheduled_date: "2025-03-14",
    starts_at: null,
  });
  assert.ok(label.includes("14 Mar 2025"));
  assert.ok(label.includes("Time unavailable"));
  assert.ok(!label.includes("00:00"));
  assert.ok(
    formatSchedule({
      scheduled_date: "2025-03-16",
      starts_at: "2025-03-16T04:00:00Z",
    }).includes("04:00 UTC"),
  );
});

test("seasons come from persisted data, with no silent fallback for a missing year", () => {
  const seasons = [
    { id: "older", year: 2024 },
    { id: "newer", year: 2025 },
  ];
  assert.equal(selectSeason(seasons, undefined)?.year, 2025);
  assert.equal(selectSeason(seasons, "2024")?.year, 2024);
  assert.equal(selectSeason(seasons, "2026"), null);
  assert.equal(selectSeason([], undefined), null);
});

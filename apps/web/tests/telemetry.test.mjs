import assert from "node:assert/strict";
import { createServer } from "node:http";
import { test } from "node:test";
import { ApiError, postEntity } from "../app/_lib/api.ts";
import {
  comparisonRequest,
  tracePaths,
  channelNumber,
  channelLabel,
  signedDelta,
} from "../app/_lib/telemetry.ts";

test("comparison POST sends only the application contract and sanitizes errors", async () => {
  const bodies = [];
  let status = 200;
  const server = createServer(async (request, response) => {
    assert.equal(request.method, "POST");
    assert.equal(request.url, "/v1/telemetry/compare");
    assert.equal(request.headers["content-type"], "application/json");
    let body = "";
    for await (const chunk of request) body += chunk;
    bodies.push(JSON.parse(body));
    response.writeHead(status, { "Content-Type": "application/json" });
    response.end(
      JSON.stringify(
        status === 200
          ? { lap_delta_ms: "-250" }
          : { detail: "private details" },
      ),
    );
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const previous = process.env.NEXT_PUBLIC_API_URL;
  process.env.NEXT_PUBLIC_API_URL = `http://127.0.0.1:${server.address().port}`;
  const body = { lap_a_id: "a", lap_b_id: "b", allow_approximate: false };
  try {
    assert.deepEqual(await postEntity("telemetry/compare", body), {
      lap_delta_ms: "-250",
    });
    status = 422;
    await assert.rejects(
      postEntity("telemetry/compare", body),
      (error) =>
        error instanceof ApiError &&
        error.status === 422 &&
        !error.message.includes("private"),
    );
    assert.deepEqual(bodies, [body, body]);
  } finally {
    if (previous === undefined) delete process.env.NEXT_PUBLIC_API_URL;
    else process.env.NEXT_PUBLIC_API_URL = previous;
    await new Promise((resolve) => server.close(resolve));
  }
});

test("selection accepts distinct imported laps and explicit approximation only", () => {
  const laps = [
    { id: "a", driver_id: "driver-a" },
    { id: "b", driver_id: "driver-b" },
  ];
  const params = {
    lap_a: "a",
    lap_b: "b",
    driver_a: "driver-a",
    driver_b: "driver-b",
  };
  assert.deepEqual(comparisonRequest(laps, params), {
    lap_a_id: "a",
    lap_b_id: "b",
    sample_count: 201,
    alignment: "normalized_distance",
    allow_approximate: false,
  });
  assert.equal(
    comparisonRequest(laps, { ...params, allow_approximate: "1" })
      .allow_approximate,
    true,
  );
  for (const changes of [
    { lap_b: "a" },
    { lap_a: "other-session" },
    { driver_a: "driver-b" },
    { alignment: "gps" },
    { allow_approximate: "true" },
  ]) {
    assert.equal(comparisonRequest(laps, { ...params, ...changes }), null);
  }
});

test("chart paths preserve gaps, isolated source points, and stepped states", () => {
  const continuous = tracePaths([0, 10, null, 30, 40, null, 50], 0, 50);
  assert.equal(
    continuous.path,
    "M0,140 L166.667,112 M500,56 L666.667,28 M1000,0",
  );
  assert.equal(continuous.dots.length, 5);
  const discrete = tracePaths([0, 1, null, 0], 0, 1, true);
  assert.equal(discrete.path, "M0,140 H333.333 V0 M1000,140");
  assert.equal(tracePaths([null, null], 0, 1).path, "");
});

test("missing, false, zero, numeric DRS codes, and delta signs stay distinct", () => {
  assert.equal(channelNumber(null), null);
  assert.equal(channelNumber(""), null);
  assert.equal(channelNumber("NaN"), null);
  assert.equal(channelNumber(false), 0);
  assert.equal(channelNumber("0"), 0);
  assert.equal(channelLabel("brake_applied", false), "Released");
  assert.equal(channelLabel("brake_applied", null), "Unavailable");
  assert.equal(channelLabel("drs_state", 8), "Code 8");
  assert.equal(channelLabel("gear", 0), "0");
  assert.equal(signedDelta("-250"), "−250 ms");
  assert.equal(signedDelta("250"), "+250 ms");
  assert.equal(signedDelta("0"), "0 ms");
  assert.equal(signedDelta(null), "Unavailable");
});

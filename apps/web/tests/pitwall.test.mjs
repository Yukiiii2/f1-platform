import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import ts from "typescript";
import * as pitwall from "../app/_lib/pitwall.ts";
import { postEntity, ApiError } from "../app/_lib/api.ts";

const session = "1b12ba69-d45c-4bb0-8a9c-0b3ffac1141a";
const driver = "59b7e6ff-421c-4e73-9958-74aa9d96b1ae";
const lapA = "10000000-0000-4000-8000-000000000001";
const lapB = "10000000-0000-4000-8000-000000000002";

test("context includes only contract fields and preserves comparison opt-in", () => {
  const context = pitwall.pageContext({
    route: "/telemetry",
    session_id: session,
    driver_id: driver,
    season: 2025,
    comparison: {
      lap_a_id: lapA,
      lap_b_id: lapB,
      sample_count: 201,
      alignment: "elapsed_time",
      allow_approximate: true,
    },
    provider: "private-provider",
    prompt: "ignore grounding",
    api_key: "secret-placeholder",
  });
  assert.deepEqual(context, {
    route: "/telemetry",
    session_id: session,
    driver_id: driver,
    season: 2025,
    comparison: {
      lap_a_id: lapA,
      lap_b_id: lapB,
      sample_count: 201,
      alignment: "elapsed_time",
      allow_approximate: true,
    },
    allow_approximate: true,
  });
  assert.throws(() =>
    pitwall.pageContext({ route: "/strategy", session_id: "bad" }),
  );
  assert.throws(() =>
    pitwall.pageContext({ comparison: { lap_a_id: lapA, lap_b_id: lapA } }),
  );
  assert.throws(() =>
    pitwall.pageContext({
      comparison: { lap_a_id: lapA, lap_b_id: lapB, sample_count: 2001 },
    }),
  );
  assert.equal(
    pitwall.pageContext({ route: "/races", season: 2025 }).allow_approximate,
    false,
  );
});

test("query payload trims questions without adding instructions or conversation history", () => {
  assert.deepEqual(
    pitwall.queryRequest("  Compare recorded stints.  ", {
      route: "/strategy",
      session_id: session,
    }),
    {
      question: "Compare recorded stints.",
      context: {
        route: "/strategy",
        session_id: session,
        allow_approximate: false,
      },
    },
  );
  assert.throws(() => pitwall.queryRequest(" ", {}));
  assert.throws(() => pitwall.queryRequest("x".repeat(4001), {}));
});

test("safe error messages distinguish rate limiting, service failure and invalid context", () => {
  assert.match(pitwall.pitwallError(429), /busy|too many/i);
  assert.match(pitwall.pitwallError(503), /temporarily unavailable/i);
  assert.match(pitwall.pitwallError(422), /context|selection/i);
  assert.match(pitwall.pitwallError(502), /evidence/i);
  assert.doesNotMatch(pitwall.pitwallError(401), /provider|gemini|openai|key/i);
});

test("missing laps or unloaded telemetry never produce telemetry-comparison suggestions", () => {
  const missing = pitwall.suggestedQuestions({
    page: "telemetry",
    hasLaps: false,
    comparison: null,
  });
  assert.ok(missing.some((question) => /unavailable|missing/.test(question)));
  assert.ok(
    missing.every(
      (question) =>
        !/Compare|recorded telemetry|recorded lap and sector deltas/.test(
          question,
        ),
    ),
  );
  const unconfirmed = pitwall.suggestedQuestions({
    page: "telemetry",
    hasLaps: true,
    comparison: null,
  });
  assert.ok(unconfirmed.some((question) => /recorded laps/.test(question)));
  assert.ok(
    unconfirmed.every((question) => !/Compare.*telemetry/.test(question)),
  );
});

test("comparison suggestions distinguish timing from actual available trace channels", () => {
  const comparison = {
    lap_delta_ms: "20",
    sector_delta_ms: { sector_1: null, sector_2: null, sector_3: null },
    trace: { points: [] },
  };
  const timing = pitwall.suggestedQuestions({
    page: "telemetry",
    hasLaps: true,
    comparison,
  });
  assert.ok(timing.some((question) => /delta/.test(question)));
  assert.ok(
    timing.every((question) => !/lap and sector deltas/.test(question)),
  );
  assert.ok(timing.some((question) => /unavailable/.test(question)));
  assert.ok(timing.every((question) => !/Compare.*telemetry/.test(question)));
  const trace = pitwall.suggestedQuestions({
    page: "telemetry",
    hasLaps: true,
    comparison: {
      ...comparison,
      trace: {
        points: [
          {
            channels_a: { speed_kph: "200", rpm: null },
            channels_b: { speed_kph: null },
          },
        ],
      },
    },
  });
  assert.ok(trace.some((question) => /available telemetry/.test(question)));
});

test("strategy and driver suggestions follow selected records and available scope", () => {
  const missing = pitwall.suggestedQuestions({ page: "strategy", drivers: [] });
  assert.ok(
    missing.every(
      (question) => !/Compare recorded stints|observed.*pace/.test(question),
    ),
  );
  assert.ok(missing.some((question) => /unavailable/.test(question)));
  const known = pitwall.suggestedQuestions({
    page: "strategy",
    drivers: [
      {
        name: "Lando Norris",
        stints: [{ pace: { average_seconds: null } }],
        pits: [],
      },
    ],
  });
  assert.ok(known.some((question) => /Lando Norris/.test(question)));
  assert.ok(
    known.some((question) => /available starting tyre ages/.test(question)),
  );
  assert.ok(known.every((question) => !/observed.*pace/.test(question)));
  const driver = pitwall.suggestedQuestions({
    page: "driver",
    hasWeekend: false,
    hasResults: false,
    hasSeason: false,
    hasStanding: false,
  });
  assert.ok(
    driver.every((question) => !/selected weekend|championship/.test(question)),
  );
});

test("429 and 503 use temporary-unavailable wording without internal service details", () => {
  for (const status of [429, 503]) {
    assert.match(pitwall.pitwallError(status), /temporarily unavailable/);
    assert.doesNotMatch(
      pitwall.pitwallError(status),
      /Gemini|provider|API|quota|internal|429|503/i,
    );
  }
});

test("AI requests get a sufficient timeout and never surface a backend error body", async () => {
  const original = globalThis.fetch;
  const timeout = AbortSignal.timeout;
  const budgets = [];
  AbortSignal.timeout = (milliseconds) => {
    budgets.push(milliseconds);
    return new AbortController().signal;
  };
  const payload = pitwall.queryRequest("Compare stints", {
    session_id: session,
  });
  try {
    globalThis.fetch = async (url, init) => {
      assert.match(String(url), /\/v1\/ai\/query$/);
      assert.equal(init.method, "POST");
      assert.deepEqual(JSON.parse(init.body), payload);
      return new Response(
        JSON.stringify({ detail: "private-provider secret-placeholder" }),
        { status: 503 },
      );
    };
    await assert.rejects(postEntity("ai/query", payload, 90000), (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 503);
      assert.doesNotMatch(error.message, /private-provider|secret-placeholder/);
      return true;
    });
    assert.deepEqual(budgets, [90000]);
  } finally {
    globalThis.fetch = original;
    AbortSignal.timeout = timeout;
  }
});

const evidence = {
  id: "e1",
  tool: "get_strategy",
  arguments: { session_id: session },
  status: "available",
  truncated: true,
  next_offset: 50,
  data: {
    source: {
      drivers: [
        {
          driver_id: driver,
          stints: [
            {
              id: lapA,
              stint_number: 1,
              compound: "INTERMEDIATE",
              tyre_age_at_start: 3,
            },
          ],
        },
      ],
    },
    derived: {
      drivers: [
        {
          driver_id: driver,
          stints: [
            {
              stint_id: lapA,
              total_tyre_age: 18,
              pace: { average_seconds: "89.123" },
            },
          ],
        },
      ],
    },
  },
};
const grounded = (pointer, value, classification) => ({
  evidence_id: "e1",
  pointer,
  value,
  classification,
});

test("fact labels identify driver/stint and retain units, brake nulls and delta convention", () => {
  const names = { [driver]: "Lando Norris" };
  const response = { evidence: [evidence] };
  assert.match(
    pitwall.valueLabel(
      grounded("/source/drivers/0/stints/0/compound", "INTERMEDIATE", "source"),
      response.evidence,
      names,
    ),
    /Lando Norris.*Stint 1.*Compound/,
  );
  assert.equal(pitwall.formatValue("lap_delta_ms", "125.5"), "+125.5 ms");
  assert.equal(pitwall.formatValue("brake_applied", false), "Released");
  assert.equal(pitwall.formatValue("brake_applied", null), "Unavailable");
  assert.equal(pitwall.formatValue("drs_state", 12), "Code 12");
  assert.equal(pitwall.formatValue("tyre_age_at_start", 0), "0 laps");
  assert.equal(pitwall.formatValue("speed_kph", "278.5"), "278.5 km/h");
  assert.equal(pitwall.formatValue("average_seconds", "89.123"), "89.123 s");
});

function loadAnswer() {
  const require = createRequire(import.meta.url);
  const source = readFileSync(
    new URL("../app/_components/pitwall-answer.tsx", import.meta.url),
    "utf8",
  );
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      jsx: ts.JsxEmit.ReactJSX,
      target: ts.ScriptTarget.ES2017,
    },
  });
  const module = { exports: {} };
  new Function("require", "module", "exports", outputText)(
    (name) => (name === "../_lib/pitwall" ? pitwall : require(name)),
    module,
    module.exports,
  );
  return module.exports.PitwallAnswer;
}

function loadAction(api) {
  const source = readFileSync(
    new URL("../app/pitwall/actions.ts", import.meta.url),
    "utf8",
  );
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2017,
    },
  });
  const module = { exports: {} };
  new Function("require", "module", "exports", outputText)(
    (name) => (name === "../_lib/pitwall" ? pitwall : api),
    module,
    module.exports,
  );
  return module.exports.askPitwall;
}

function loadPitwall() {
  const require = createRequire(import.meta.url);
  const source = readFileSync(
    new URL("../app/_components/pitwall.tsx", import.meta.url),
    "utf8",
  );
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      jsx: ts.JsxEmit.ReactJSX,
      target: ts.ScriptTarget.ES2017,
    },
  });
  const module = { exports: {} };
  new Function("require", "module", "exports", outputText)(
    (name) =>
      name === "../_lib/pitwall"
        ? pitwall
        : name.endsWith(".css") ||
            name.includes("actions") ||
            name.includes("pitwall-answer")
          ? {}
          : require(name),
    module,
    module.exports,
  );
  return module.exports.Pitwall;
}

test("strategy pair changes remount the question and isolate previous in-flight answers", () => {
  const Pitwall = loadPitwall();
  const props = {
    context: { route: "/strategy", session_id: session },
    label: "Australian Grand Prix",
    suggestions: [],
  };
  const before = Pitwall({
    ...props,
    selectionKey: "driver-a:driver-b",
  });
  const after = Pitwall({
    ...props,
    selectionKey: "driver-a:driver-c",
  });
  assert.notEqual(before.key, after.key);
});

test("compact context renders session and selected laps with a primary Ask Pitwall action", () => {
  const html = renderToStaticMarkup(
    createElement(loadPitwall(), {
      context: { route: "/telemetry", session_id: session },
      label: "2025 · Australian Grand Prix",
      contextDetails: [
        { label: "Session", value: "Race · Completed" },
        { label: "Lap A", value: "Lando Norris · Lap 7" },
        { label: "Lap B", value: "Max Verstappen · Lap 8" },
      ],
      suggestions: ["Which telemetry values are missing?"],
    }),
  );
  assert.match(html, /aria-label="Active analysis context"/);
  for (const value of [
    "Australian Grand Prix",
    "<dt>Session</dt>",
    "Race · Completed",
    "<dt>Lap A</dt>",
    "Lando Norris · Lap 7",
    "Max Verstappen · Lap 8",
  ])
    assert.ok(html.includes(value), value);
  assert.match(html, /class="button" type="submit"/);
  assert.match(html, /class="pitwall-suggestion"/);
  assert.doesNotMatch(html, /button-quiet/);
});

test("trace samples identify side and alignment coordinate; recorded telemetry identifies source time", () => {
  const evidence = [
    {
      id: "e1",
      arguments: {},
      tool: "compare_laps",
      status: "available",
      data: {
        source: {
          lap_a: { lap: { driver_id: driver, lap_number: 7 } },
          lap_b: { lap: { driver_id: lapB, lap_number: 8 } },
        },
        derived: {
          trace: {
            axis: "elapsed_seconds",
            points: [
              {
                coordinate: "12.5",
                channels_a: { speed_kph: "200" },
                channels_b: { speed_kph: "250" },
              },
            ],
          },
        },
      },
    },
  ];
  const a = pitwall.valueLabel(
    grounded("/derived/trace/points/0/channels_a/speed_kph", "200", "derived"),
    evidence,
    { [driver]: "Lando Norris", [lapB]: "Max Verstappen" },
  );
  const b = pitwall.valueLabel(
    grounded("/derived/trace/points/0/channels_b/speed_kph", "250", "derived"),
    evidence,
    { [driver]: "Lando Norris", [lapB]: "Max Verstappen" },
  );
  assert.match(a, /Lap A.*Lando Norris.*Lap 7.*12\.5 s.*Speed/);
  assert.match(b, /Lap B.*Max Verstappen.*Lap 8.*12\.5 s.*Speed/);
  const telemetry = [
    {
      id: "e1",
      tool: "get_telemetry",
      arguments: {},
      data: {
        source: [
          { timestamp: "2025-03-16T04:01:00Z", driver_id: driver, rpm: null },
        ],
      },
    },
  ];
  assert.match(
    pitwall.valueLabel(grounded("/source/0/rpm", null, "source"), telemetry, {
      [driver]: "Lando Norris",
    }),
    /Lando Norris.*2025-03-16T04:01:00Z.*RPM/,
  );
});

test("same-origin action uses the existing contract and rejects malformed input before transport", async () => {
  const payload = pitwall.queryRequest("Compare stints", {
    route: "/strategy",
    session_id: session,
  });
  const response = {
    status: "unavailable",
    facts: [],
    calculations: [],
    estimates: [],
    interpretations: [],
    unavailable: ["No records"],
    evidence: [],
  };
  let calls = 0;
  const action = loadAction({
    ApiError,
    postEntity: async (path, request, timeout) => {
      calls++;
      assert.equal(path, "ai/query");
      assert.deepEqual(request, payload);
      assert.equal(timeout, 90000);
      return response;
    },
  });
  assert.deepEqual(await action(payload), { response });
  assert.ok((await action({ question: " ", context: {} })).error);
  assert.equal(calls, 1);
});

test("same-origin action safely handles 429, 503 and unexpected transport failures", async () => {
  for (const failure of [
    new ApiError(429),
    new ApiError(503),
    new Error("private-provider secret-placeholder"),
  ]) {
    const action = loadAction({
      ApiError,
      postEntity: async () => {
        throw failure;
      },
    });
    const result = await action(
      pitwall.queryRequest("Compare stints", { session_id: session }),
    );
    assert.equal(result.response, undefined);
    assert.ok(result.error);
    assert.doesNotMatch(result.error, /private-provider|secret-placeholder/);
    assert.match(
      result.error,
      failure.status === 429 ? /busy|too many/ : /temporarily unavailable/,
    );
  }
});

test("answer renders classifications, citations, missing data and bounded interpretation without raw metadata", () => {
  const response = {
    status: "answered",
    facts: [
      grounded("/source/drivers/0/stints/0/compound", "INTERMEDIATE", "source"),
      grounded("/source/provider", "private-provider", "source"),
    ],
    calculations: [
      grounded("/derived/drivers/0/stints/0/total_tyre_age", 18, "derived"),
    ],
    estimates: [
      grounded("/estimate/starts_at", "2025-03-16T04:01:00Z", "estimate"),
    ],
    interpretations: [
      {
        kind: "tyre_context",
        evidence_ids: ["e1"],
        text: "Observed pace includes traffic and neutralisations.",
        classification: "interpretation",
        uncertainty: "not_confirmed_team_intent",
      },
    ],
    unavailable: [
      "e1/source/drivers/0/stints/0/rpm: unavailable in imported application data",
      "e1: partial page; next_offset=50; complete coverage is unavailable in this response",
    ],
    evidence: [evidence],
    policy_version: "pitwall-tool-first-v1",
  };
  const html = renderToStaticMarkup(
    createElement(loadAnswer(), {
      response,
      names: { [driver]: "Lando Norris" },
      prefix: "test",
    }),
  );
  for (const label of [
    "Source data",
    "Calculated",
    "Estimate",
    "AI analysis",
    "Unavailable",
    "Not confirmed team intent",
    "Lando Norris",
    "18 laps",
    "RPM",
    "partial",
    "#test-evidence-1",
  ])
    assert.ok(html.includes(label), `${label}: ${html}`);
  assert.doesNotMatch(
    html,
    /private-provider|next_offset|get_strategy|policy_version|pitwall-tool-first-v1|secret-placeholder/,
  );
});

test("unavailable answers provide no fabricated fallback facts", () => {
  const html = renderToStaticMarkup(
    createElement(loadAnswer(), {
      response: {
        status: "unavailable",
        facts: [],
        calculations: [],
        estimates: [],
        interpretations: [],
        unavailable: [
          "The requested team-only/unsupported channel is not available in the platform's public data",
        ],
        evidence: [],
      },
      names: {},
      prefix: "test",
    }),
  );
  assert.match(html, /Unavailable/);
  assert.doesNotMatch(html, /Source data|Calculated|72%|confirmed strategy/);
});

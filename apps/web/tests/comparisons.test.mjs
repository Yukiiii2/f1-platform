import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import * as api from "../app/_lib/api.ts";
import * as format from "../app/_lib/format.ts";
import * as contracts from "../app/_lib/contracts.ts";
import * as telemetry from "../app/_lib/telemetry.ts";
import * as strategy from "../app/_lib/strategy.ts";
import { authHref } from "../app/_lib/auth.ts";
import {
  telemetryPreset,
  strategyPreset,
  comparisonError,
} from "../app/_lib/saved-comparisons.ts";

const id = "11111111-1111-4111-8111-111111111111";
const context = { season: 2025, event_id: id, session_id: id };
const authAPI = {
  sessionHeaders: async () => ({
    "X-F1-Auth": "1",
    Cookie: "f1_session=test-session",
  }),
  accountState: async () => ({ user: { id: "account", username: "driver-a" } }),
};
const signIn = {
  SignInRequired: () => createElement("p", {}, "Sign in required"),
};
const laps = [
  { id: "lap-a", driver_id: "norris" },
  { id: "lap-b", driver_id: "max" },
];
const pair = {
  lap_a_id: "lap-a",
  lap_b_id: "lap-b",
  alignment: "elapsed_time",
  allow_approximate: true,
};
const saved = {
  id,
  title: "Wet race laps",
  comparison_type: "telemetry_laps",
  source_route: "/telemetry",
  configuration: {
    ...context,
    version: 1,
    driver_a_id: "norris",
    driver_b_id: "max",
    ...pair,
  },
  created_at: "2025-03-17T00:00:00Z",
  updated_at: "2025-03-17T00:00:00Z",
  event_name: "Australian Grand Prix",
  session_name: "race",
  driver_a_name: "Lando Norris",
  driver_b_name: "Max Verstappen",
  lap_a_number: 5,
  lap_b_number: 6,
  availability: "partial",
  notices: ["Some timing is estimated."],
  open_url: "/telemetry?season=2025&compare=1",
};

function load(path, dependencies = {}) {
  const require = createRequire(import.meta.url);
  const { outputText } = ts.transpileModule(
    readFileSync(new URL(`../app/${path}`, import.meta.url), "utf8"),
    {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        jsx: ts.JsxEmit.ReactJSX,
      },
    },
  );
  const module = { exports: {} };
  new Function("require", "module", "exports", outputText)(
    (name) => dependencies[name] ?? require(name),
    module,
    module.exports,
  );
  return module.exports;
}
const link = {
  default: ({ prefetch, children, ...props }) =>
    createElement("a", props, children),
};
const ui = {
  PageHeading: ({ title, intro }) =>
    createElement(
      "header",
      {},
      createElement("h1", {}, title),
      createElement("p", {}, intro),
    ),
  EmptyState: ({ title, children }) =>
    createElement("section", {}, createElement("h2", {}, title), children),
};

test("telemetry preset preserves exact lap/driver/alignment settings", () => {
  assert.deepEqual(telemetryPreset(context, laps, pair), {
    comparison_type: "telemetry_laps",
    configuration: saved.configuration,
  });
  assert.equal(telemetryPreset(context, laps.slice(0, 1), pair), null);
});

test("strategy preset preserves explicit provider-scoped pair, never single driver", () => {
  const rows = [
    { driver_id: "norris", provider: "openf1" },
    { driver_id: "max", provider: "openf1" },
  ];
  const preset = strategyPreset(context, rows);
  assert.equal(preset.configuration.driver_b_id, "max");
  assert.equal(preset.configuration.provider_b, "openf1");
  assert.equal(strategyPreset(context, rows.slice(0, 1)), null);
});

test("Saved Comparisons shows context, metadata, open, rename, delete and unavailable records", async () => {
  const Manage = load("comparisons/manage-comparisons.tsx", {
    "next/link": link,
    "next/navigation": { useRouter: () => ({ refresh() {} }) },
    "./actions": {},
    "../_lib/saved-comparisons": { comparisonError },
  }).ManageComparisons;
  const Page = load("comparisons/page.tsx", {
    "../_lib/auth-api": authAPI,
    "../_components/sign-in-required": signIn,
    "next/link": link,
    "../_lib/api": {
      getComparisonPage: async () => [
        saved,
        {
          ...saved,
          id: "missing",
          title: "Removed lap",
          availability: "unavailable",
          open_url: null,
        },
      ],
    },
    "../_lib/format": { single: (value) => value },
    "../_components/ui": ui,
    "./manage-comparisons": { ManageComparisons: Manage },
    "./comparisons.css": {},
  }).default;
  const html = renderToStaticMarkup(
    await Page({ searchParams: Promise.resolve({ season: "2025" }) }),
  );
  for (const text of [
    "Saved Comparisons",
    "Australian Grand Prix",
    "Lando Norris",
    "Max Verstappen",
    "Lap 5",
    "Partial",
    "Unavailable",
    "Rename",
    "Delete",
    "Created",
    "Updated",
  ])
    assert.ok(html.includes(text), text);
  assert.ok(html.includes(`/comparisons/${id}/open?season=2025`));
  assert.ok(!html.includes("/comparisons/missing/open"));
});

test("open revalidates on server and restores URL; missing references never redirect", async () => {
  let row = saved;
  const Page = load("comparisons/[comparisonId]/open/page.tsx", {
    "../../../_lib/auth-api": authAPI,
    "../../../_components/sign-in-required": signIn,
    "next/link": link,
    "next/navigation": {
      redirect: (url) => {
        throw new Error(`redirect:${url}`);
      },
    },
    "../../../_lib/api": {
      getSavedComparison: async () => row,
      ApiError: api.ApiError,
    },
    "../../../_components/ui": ui,
  }).default;
  const props = { params: Promise.resolve({ comparisonId: id }) };
  await assert.rejects(
    Page(props),
    /redirect:\/telemetry\?season=2025&compare=1/,
  );
  row = {
    ...saved,
    availability: "unavailable",
    open_url: null,
    notices: ["A saved lap is no longer available."],
  };
  const html = renderToStaticMarkup(await Page(props));
  assert.ok(html.includes("A saved lap is no longer available"));
  assert.ok(html.includes("No replacement"));
});

test("save, rename and delete server actions use only application API with safe failures", async () => {
  const actions = load("comparisons/actions.ts", {
    "../_lib/auth-api": authAPI,
    "../_lib/api": api,
    "../_lib/saved-comparisons": { comparisonError },
  });
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url: String(url), ...options });
    return options.method === "DELETE"
      ? new Response(null, { status: 204 })
      : new Response(JSON.stringify(saved));
  };
  try {
    assert.equal(
      (
        await actions.saveComparison({
          title: saved.title,
          ...telemetryPreset(context, laps, pair),
        })
      ).response.id,
      id,
    );
    assert.equal(
      (await actions.renameComparison(id, "Renamed")).response.id,
      id,
    );
    assert.equal((await actions.deleteComparison(id)).success, true);
    assert.deepEqual(
      calls.map((call) => call.method),
      ["POST", "PATCH", "DELETE"],
    );
    assert.equal(JSON.parse(calls[1].body).title, "Renamed");
    assert.ok(
      calls.every((call) => call.headers.Cookie === "f1_session=test-session"),
    );
    globalThis.fetch = async () =>
      new Response("internal secret/provider detail", { status: 503 });
    const failure = await actions.saveComparison({
      title: saved.title,
      ...telemetryPreset(context, laps, pair),
    });
    assert.match(failure.error, /temporarily unavailable/i);
    assert.ok(!failure.error.includes("secret"));
  } finally {
    globalThis.fetch = original;
  }
});

test("save form is labelled and navigation preserves selected season", () => {
  const Save = load("_components/save-comparison.tsx", {
    "../_lib/auth": { authHref },
    "next/link": link,
    "../comparisons/actions": {},
    "../_lib/saved-comparisons": { comparisonError },
  }).SaveComparison;
  const html = renderToStaticMarkup(
    createElement(Save, {
      preset: telemetryPreset(context, laps, pair),
      suggestedTitle: "Norris vs Verstappen",
      signedIn: true,
      returnTo: "/telemetry?season=2025",
    }),
  );
  assert.ok(html.includes("Save comparison"));
  assert.ok(html.includes("Comparison title"));
  const Nav = load("_components/navigation.tsx", {
    "next/link": link,
    "next/navigation": {
      usePathname: () => "/comparisons",
      useSearchParams: () => new URLSearchParams("season=2010"),
    },
    "../_lib/format": { seasonHref: (path, year) => `${path}?season=${year}` },
  }).Navigation;
  assert.match(
    renderToStaticMarkup(createElement(Nav)),
    /href="\/comparisons\?season=2010"[^>]*aria-current="page"[^>]*>Saved Comparisons/,
  );
});

function find(tree, predicate) {
  if (!tree || typeof tree !== "object") return null;
  if (predicate(tree)) return tree;
  for (const child of [tree.props?.children].flat(Infinity)) {
    const result = find(child, predicate);
    if (result) return result;
  }
  return null;
}

test("save/rename/delete controls invoke their actions and refresh only after success", async () => {
  let states = [];
  let cursor = 0;
  let refreshed = 0;
  const pending = [];
  const calls = [];
  const hooks = {
    useId: () => "preset-control",
    useState: (initial) => {
      const index = cursor++;
      if (states[index] === undefined) states[index] = initial;
      return [
        states[index],
        (value) => {
          states[index] = value;
        },
      ];
    },
    useTransition: () => [false, (action) => pending.push(action())],
  };
  const actionMocks = {
    saveComparison: async (request) => {
      calls.push(["save", request]);
      return { response: saved };
    },
    renameComparison: async (...args) => {
      calls.push(["rename", ...args]);
      return { response: saved };
    },
    deleteComparison: async (...args) => {
      calls.push(["delete", ...args]);
      return { success: true };
    },
  };
  const Save = load("_components/save-comparison.tsx", {
    "../_lib/auth": { authHref },
    react: hooks,
    "next/link": link,
    "../comparisons/actions": actionMocks,
    "../_lib/saved-comparisons": { comparisonError },
  }).SaveComparison;
  const tree = Save({
    preset: telemetryPreset(context, laps, pair),
    suggestedTitle: "Lap pair",
    signedIn: true,
    returnTo: "/telemetry?season=2025",
  });
  find(tree, (node) => node.type === "form").props.onSubmit({
    preventDefault() {},
  });
  await Promise.all(pending.splice(0));
  assert.equal(calls[0][1].title, "Lap pair");
  assert.equal(calls[0][1].configuration.lap_b_id, "lap-b");
  const Manage = load("comparisons/manage-comparisons.tsx", {
    react: hooks,
    "next/link": link,
    "next/navigation": { useRouter: () => ({ refresh: () => refreshed++ }) },
    "./actions": actionMocks,
    "../_lib/saved-comparisons": { comparisonError },
  }).ManageComparisons;
  const rowElement = Manage({ rows: [saved] }).props.children[0];
  cursor = 0;
  states = [true, false, "Renamed pair", null];
  const editing = rowElement.type(rowElement.props);
  find(editing, (node) => node.type === "form").props.onSubmit({
    preventDefault() {},
  });
  await Promise.all(pending.splice(0));
  assert.deepEqual(calls[1], ["rename", id, "Renamed pair"]);
  cursor = 0;
  states = [false, true, saved.title, null];
  const confirming = rowElement.type(rowElement.props);
  find(
    confirming,
    (node) =>
      node.type === "button" && node.props.children === "Confirm delete",
  ).props.onClick();
  await Promise.all(pending.splice(0));
  assert.deepEqual(calls[2], ["delete", id]);
  assert.equal(refreshed, 2);
});

test("existing telemetry and strategy pages save actual selected state, not a new analysis", async () => {
  const recordedLaps = laps.map((lap, index) => ({
    ...lap,
    lap_number: index + 5,
  }));
  const drivers = new Map([
    ["norris", { id: "norris", given_name: "Lando", family_name: "Norris" }],
    ["max", { id: "max", given_name: "Max", family_name: "Verstappen" }],
  ]);
  const event = {
    id,
    name: "Australian Grand Prix",
    season_id: "season",
    round: 1,
  };
  const session = { id, event_id: id, type: "race", status: "completed" };
  const data = {
    seasonContext: async () => ({
      seasons: [],
      season: { id: "season", year: 2025 },
    }),
    seasonEvents: async () => [event],
    eventSessions: async () => [session],
    references: async () => drivers,
  };
  const presets = [];
  const common = {
    "../_lib/auth-api": authAPI,
    "next/link": link,
    "next/navigation": {
      notFound: () => {
        throw new Error("notFound");
      },
    },
    "../_lib/data": data,
    "../_lib/format": format,
    "../_lib/contracts": contracts,
    "../_components/ui": {
      ...ui,
      SectionHeading: () => null,
      SeasonSelector: () => null,
      NoSeason: () => null,
    },
    "../_components/pitwall": { Pitwall: () => null },
    "../_components/session-updates": { SessionUpdates: () => null },
    "../_lib/pitwall": { suggestedQuestions: () => [] },
    "../_components/save-comparison": {
      SaveComparison: ({ preset }) => {
        presets.push(preset);
        return createElement("span", {}, "Save comparison");
      },
    },
    "../_lib/saved-comparisons": { telemetryPreset, strategyPreset },
  };
  const Telemetry = load("telemetry/page.tsx", {
    ...common,
    "../_lib/api": {
      ApiError: api.ApiError,
      getList: async () => recordedLaps,
      postEntity: async () => ({}),
    },
    "../_lib/telemetry": telemetry,
    "./compare-form": { CompareForm: () => null },
    "./comparison-view": { ComparisonView: () => null },
    "./telemetry.css": {},
  }).default;
  const telemetryQuery = {
    season: "2025",
    event: id,
    session: id,
    driver_a: "norris",
    driver_b: "max",
    lap_a: "lap-a",
    lap_b: "lap-b",
    alignment: "elapsed_time",
    allow_approximate: "1",
    compare: "1",
  };
  renderToStaticMarkup(
    await Telemetry({ searchParams: Promise.resolve(telemetryQuery) }),
  );
  assert.deepEqual(presets.pop(), telemetryPreset(context, laps, pair));
  renderToStaticMarkup(
    await Telemetry({
      searchParams: Promise.resolve({ ...telemetryQuery, compare: undefined }),
    }),
  );
  assert.equal(presets.length, 0);
  const rows = [
    { driver_id: "norris", provider: "openf1" },
    { driver_id: "max", provider: "openf1" },
  ];
  const Strategy = load("strategy/page.tsx", {
    ...common,
    "../_lib/api": {
      ApiError: api.ApiError,
      getSessionStrategy: async () => ({ drivers: rows }),
    },
    "../_lib/strategy": strategy,
    "./strategy-view": { StrategyView: () => null },
    "./strategy.css": {},
  }).default;
  renderToStaticMarkup(
    await Strategy({
      searchParams: Promise.resolve({
        season: "2025",
        event: id,
        session: id,
        a: "openf1:max",
        b: "openf1:norris",
      }),
    }),
  );
  assert.equal(presets.pop().configuration.driver_a_id, "max");
  renderToStaticMarkup(
    await Strategy({
      searchParams: Promise.resolve({
        season: "2025",
        event: id,
        session: id,
        a: "openf1:max",
        b: "",
      }),
    }),
  );
  assert.equal(presets.length, 0);
});

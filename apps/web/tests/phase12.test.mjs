import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import { ApiError } from "../app/_lib/api.ts";
import * as format from "../app/_lib/format.ts";

const require = createRequire(import.meta.url);
function load(path, dependencies) {
  const { outputText } = ts.transpileModule(
    readFileSync(new URL(path, import.meta.url), "utf8"),
    {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        jsx: ts.JsxEmit.ReactJSX,
        target: ts.ScriptTarget.ES2022,
      },
    },
  );
  const compiledModule = { exports: {} };
  new Function("require", "module", "exports", outputText)(
    (name) => dependencies[name] ?? require(name),
    compiledModule,
    compiledModule.exports,
  );
  return compiledModule.exports;
}

function data(api) {
  return load("../app/_lib/data.ts", {
    "next/navigation": {
      notFound() {
        throw new Error("not found");
      },
    },
    "./api": { ApiError, ...api },
    "./format": format,
  });
}

function weekend(id, date) {
  return {
    id,
    scheduled_date: date,
    starts_at: null,
    circuit_id: "circuit",
    name: `Race ${id}`,
    round: 1,
  };
}

test("completed date-only races are excluded from next weekends even on today's date", async () => {
  const requests = [];
  const api = data({
    async getList(path) {
      requests.push(path);
      return [
        {
          type: "race",
          status: path.includes("done") ? "completed" : "upcoming",
        },
      ];
    },
  });
  const done = weekend("done", "2026-10-10");
  const next = weekend("next", "2026-10-17");
  const result = await api.homeCalendar(
    [done, next],
    new Date("2026-10-10T12:00:00Z"),
  );
  assert.equal(result.featured.id, "next");
  assert.deepEqual(
    result.calendar.map((row) => row.id),
    ["next"],
  );
  assert.deepEqual(requests, ["events/done/sessions", "events/next/sessions"]);
});

test("finished season retains completed race with accurate Home caption and no next-weekends list", async () => {
  const today = new Date().toISOString().slice(0, 10);
  const done = weekend("done", today);
  const api = data({
    async getList(path) {
      if (path === "seasons") return [{ id: "season", year: 2026 }];
      if (path === "events") return [done];
      if (path.startsWith("standings")) return [];
      if (path === "circuits")
        return [{ id: "circuit", name: "Albert Park", country: "Australia" }];
      if (path === "events/done/sessions")
        return [{ type: "race", status: "completed" }];
      throw new Error(`Unexpected request ${path}`);
    },
    async getEntity() {
      return { id: "circuit", name: "Albert Park", country: "Australia" };
    },
  });
  const component = ({ children, title, value }) =>
    createElement("div", null, title, value, children);
  const { default: Home } = load("../app/page.tsx", {
    "next/link": {
      default: ({ children, href }) => createElement("a", { href }, children),
    },
    "./_lib/data": api,
    "./_lib/format": format,
    "./_components/car-showcase": { CarShowcase: () => null },
    "./_components/ui": Object.fromEntries(
      [
        "EmptyState",
        "NoSeason",
        "PageHeading",
        "SeasonSelector",
        "SectionHeading",
        "Status",
      ].map((name) => [name, component]),
    ),
    "./_components/tables": Object.fromEntries(
      ["ConstructorStandingsTable", "DriverStandingsTable", "EventTable"].map(
        (name) => [name, component],
      ),
    ),
  });
  const html = renderToStaticMarkup(
    await Home({ searchParams: Promise.resolve({}) }),
  );
  assert.match(html, /Latest completed weekend/);
  assert.doesNotMatch(html, /Next on the calendar/);
});

test("identity resolution batches unique IDs, preserves missing-data errors and skips empty requests", async () => {
  const requests = [];
  const api = data({
    async getList(resource, query) {
      requests.push([resource, query]);
      return query.ids
        .split(",")
        .filter((id) => id !== "missing")
        .map((id) => ({ id }));
    },
    async getEntity() {
      assert.fail("Per-identity fetches amplify requests");
    },
  });
  const rows = await api.references("drivers", [
    "norris",
    "verstappen",
    "norris",
  ]);
  assert.equal(rows.size, 2);
  assert.deepEqual(requests, [["drivers", { ids: "norris,verstappen" }]]);
  await api.references("teams", []);
  assert.equal(requests.length, 1);
  await assert.rejects(
    api.references("drivers", ["missing"]),
    (error) => error instanceof ApiError && error.status === 404,
  );
  requests.length = 0;
  await api.references(
    "drivers",
    Array.from({ length: 201 }, (_, index) => `driver${index}`),
  );
  assert.equal(requests.length, 2);
  assert.ok(requests.every(([, query]) => query.ids.split(",").length <= 200));
});

test("root setup documents existing Pitwall entry and explicit automatic worker scheduling", () => {
  const readme = readFileSync(
    new URL("../../../README.md", import.meta.url),
    "utf8",
  );
  assert.doesNotMatch(
    readme,
    /no Pitwall frontend yet|no scheduler .* implemented/i,
  );
  assert.match(readme, /\/pitwall/);
  assert.match(readme, /app\.workers --watch/);
  assert.match(readme, /explicit.*registration|registered.*session/i);
});

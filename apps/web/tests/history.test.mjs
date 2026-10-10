import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import * as formatting from "../app/_lib/format.ts";
import { selectSeason, seasonHref } from "../app/_lib/format.ts";

const source = (path) =>
  readFileSync(new URL(`../app/${path}`, import.meta.url), "utf8");

function component(path, stubs = {}) {
  const require = createRequire(import.meta.url);
  const { outputText } = ts.transpileModule(source(path), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      jsx: ts.JsxEmit.ReactJSX,
      target: ts.ScriptTarget.ES2017,
    },
  });
  const module = { exports: {} };
  const dependencies = {
    "next/link": {
      default: ({ prefetch, children, ...props }) =>
        createElement("a", props, children),
    },
    "../_lib/format": formatting,
    "../_lib/contracts": { statusNames: {} },
    ...stubs,
  };
  new Function("require", "module", "exports", outputText)(
    (name) => dependencies[name] ?? require(name),
    module,
    module.exports,
  );
  return module.exports;
}

test("selector renders imported/partial availability and drops stale weekend/lap state", () => {
  const { SeasonSelector } = component("_components/ui.tsx");
  const seasons = [
    { id: "latest", year: 2025, availability: "imported" },
    { id: "old", year: 2010, availability: "partial" },
    { id: "empty", year: 2000, availability: "unavailable" },
  ];
  const html = renderToStaticMarkup(
    createElement(SeasonSelector, {
      seasons,
      selected: seasons[1],
      action: "/races",
    }),
  );
  assert.match(html, /2010 · Partially imported/);
  assert.match(html, /2025 · Imported/);
  assert.doesNotMatch(html, /2000|name="event"|name="session"|name="lap_a"/);
  assert.match(html, /action="\/races"/);
  assert.match(html, /value="2010" selected/);
});

test("navigation and home brand preserve historical year without page-specific selectors", () => {
  const { Navigation, SeasonHomeLink } = component(
    "_components/navigation.tsx",
    {
      "next/navigation": {
        usePathname: () => "/races",
        useSearchParams: () =>
          new URLSearchParams("season=2010&session=old-lap"),
      },
    },
  );
  const html = renderToStaticMarkup(createElement(Navigation));
  for (const route of [
    "/",
    "/races",
    "/drivers",
    "/standings",
    "/telemetry",
    "/strategy",
    "/pitwall",
  ])
    assert.ok(html.includes(`href="${route}?season=2010"`));
  assert.doesNotMatch(html, /old-lap|session=/);
  assert.match(
    renderToStaticMarkup(createElement(SeasonHomeLink, null, "Home")),
    /href="\/\?season=2010"/,
  );
});

test("Pitwall unavailable historical context never silently opens the latest season", async () => {
  const ui = component("_components/ui.tsx");
  const { default: Page } = component("pitwall/page.tsx", {
    "../_components/ui": ui,
    "../_lib/data": {
      seasonContext: async () => ({
        seasons: [{ id: "latest", year: 2025, availability: "imported" }],
        season: null,
      }),
    },
    "./pitwall.css": {},
  });
  const html = renderToStaticMarkup(
    await Page({ searchParams: Promise.resolve({ season: "2000" }) }),
  );
  for (const route of ["/races", "/drivers", "/telemetry", "/strategy"])
    assert.ok(html.includes(`href="${route}?season=2000"`));
  assert.match(html, /No race data for this season/);
});

test("season URLs are shareable, preserve session/hash and replace an old year", () => {
  assert.equal(seasonHref("/telemetry", 2010), "/telemetry?season=2010");
  assert.equal(
    seasonHref("/races/event?session=uuid#results", 2010),
    "/races/event?session=uuid&season=2010#results",
  );
  assert.equal(
    seasonHref("/standings?season=2025&view=constructors", 2010),
    "/standings?season=2010&view=constructors",
  );
  assert.equal(seasonHref("/drivers", null), "/drivers");
});

test("unavailable seasons do not silently resolve to imported years", () => {
  const seasons = [
    { year: 2025, availability: "imported" },
    { year: 2010, availability: "partial" },
    { year: 2000, availability: "unavailable" },
  ];
  assert.equal(selectSeason(seasons, "2010")?.year, 2010);
  assert.equal(selectSeason(seasons, "2000"), null);
  assert.equal(selectSeason(seasons, "1999"), null);
  assert.equal(selectSeason(seasons)?.year, 2025);
});

test("driver directory scopes records and search to selected year", () => {
  const page = source("drivers/page.tsx");
  assert.match(page, /seasonContext/);
  assert.match(page, /season: season.year/);
  assert.match(page, /SeasonSelector/);
  assert.match(page, /name="season"/);
});

test("navigation and contextual links carry year while switches drop incompatible selectors", () => {
  assert.match(source("_components/navigation.tsx"), /seasonHref/);
  assert.match(source("_components/ui.tsx"), /Partially imported/);
  assert.match(source("_components/tables.tsx"), /seasonHref/);
  for (const page of [
    "telemetry/page.tsx",
    "strategy/page.tsx",
    "races/[eventId]/page.tsx",
    "drivers/[driverId]/page.tsx",
  ]) {
    const content = source(page);
    assert.match(content, /season.year/);
    assert.match(content, /season: season.year/);
    assert.match(content, /SeasonSelector/);
  }
  assert.match(source("pitwall/page.tsx"), /seasonHref/);
});

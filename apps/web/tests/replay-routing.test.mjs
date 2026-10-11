import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import * as api from "../app/_lib/api.ts";
import * as format from "../app/_lib/format.ts";
import * as replay from "../app/_lib/replay.ts";
import * as contracts from "../app/_lib/contracts.ts";

const eventId = "6e6750a5-7170-4052-9169-c31ba72e0924";
const raceId = "1b12ba69-d45c-4bb0-8a9c-0b3ffac1141a";
const qualifyingId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const seasonId = "b0143f2b-19fc-4562-a0cf-e67a4d494c48";
const missingId = "ffffffff-ffff-4fff-8fff-ffffffffffff";
const event = {
  id: eventId,
  name: "Australian Grand Prix",
  season_id: seasonId,
  circuit_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  round: 1,
};
const race = {
  id: raceId,
  event_id: eventId,
  type: "race",
  status: "completed",
};
const qualifying = {
  id: qualifyingId,
  event_id: eventId,
  type: "qualifying",
  status: "completed",
};

function component(path, dependencies) {
  const require = createRequire(import.meta.url);
  const source = readFileSync(
    new URL(`../app/${path}`, import.meta.url),
    "utf8",
  );
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      jsx: ts.JsxEmit.ReactJSX,
    },
  });
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
const navigation = {
  notFound: () => {
    throw new Error("notFound");
  },
  redirect: (url) => {
    throw new Error(`redirect:${url}`);
  },
};
const data = component("_lib/data.ts", {
  "next/navigation": navigation,
  "./api": api,
  "./format": format,
});
const ui = component("_components/ui.tsx", {
  "next/link": link,
  "../_lib/contracts": contracts,
});
const replayUI = component("_components/race-replay.tsx", {
  "../_lib/replay": replay,
});
const shared = {
  "next/link": link,
  "next/navigation": navigation,
};
const { default: ReplayPage } = component("races/[eventId]/replay/page.tsx", {
  ...shared,
  "../../../_lib/data": data,
  "../../../_lib/api": api,
  "../../../_lib/contracts": contracts,
  "../../../_lib/format": format,
  "../../../_lib/replay": replay,
  "../../../_components/ui": ui,
  "../../../_components/race-replay": replayUI,
  "../../../_components/session-updates": { SessionUpdates: () => null },
  "../../../_components/pitwall": { Pitwall: () => null },
  "../../../_lib/pitwall": { suggestedQuestions: () => [] },
  "./replay.css": {},
});
const { default: RacePage } = component("races/[eventId]/page.tsx", {
  "../../_components/reference-actions": { ReferenceActions: () => null },
  ...shared,
  "../../_lib/data": data,
  "../../_lib/api": api,
  "../../_lib/contracts": contracts,
  "../../_lib/format": format,
  "../../_lib/replay": replay,
  "../../_components/ui": ui,
  "../../_components/tables": { ResultsTable: () => null },
  "../../_components/session-updates": { SessionUpdates: () => null },
  "../../_components/pitwall": { Pitwall: () => null },
  "../../_lib/pitwall": { suggestedQuestions: () => [] },
});

async function withAPI(
  run,
  {
    seasons = [{ id: seasonId, year: 2025, availability: "partial" }],
    capability = "partial",
  } = {},
) {
  const original = globalThis.fetch;
  const requested = [];
  globalThis.fetch = async (url) => {
    const path = new URL(url).pathname.replace(/^\/v1\//, "");
    requested.push(path);
    const records = {
      [`events/${eventId}`]: event,
      seasons,
      [`events/${eventId}/sessions`]: [qualifying, race],
      [`circuits/${event.circuit_id}`]: {
        id: event.circuit_id,
        name: "Albert Park",
        country: "Australia",
      },
      [`sessions/${raceId}/results`]: [],
      [`sessions/${qualifyingId}/results`]: [],
      [`sessions/${raceId}/replay`]: {
        session: race,
        event_id: eventId,
        event_name: event.name,
        season: 2025,
        capability,
        provisional: false,
        provider: "openf1",
        duration_seconds: 20,
        starts_at: "2025-03-16T04:00:00Z",
        ends_at: "2025-03-16T04:00:20Z",
        drivers: [
          {
            driver: {
              id: "driver",
              code: "NOR",
              given_name: "Lando",
              family_name: "Norris",
            },
            team: null,
            positions: [{ elapsed_seconds: 0, position: 1 }],
            intervals: [],
            laps: [],
            pits: [],
          },
        ],
        race_control: [],
        quality: { notes: [], max_hold_seconds: 30 },
      },
    };
    return new Response(JSON.stringify(records[path] ?? {}), {
      status: path in records ? 200 : 404,
    });
  };
  try {
    await run(requested);
  } finally {
    globalThis.fetch = original;
  }
}
const props = (query = { season: "2025" }, id = eventId) => ({
  params: Promise.resolve({ eventId: id }),
  searchParams: Promise.resolve(query),
});

test("same existing event resolves on race detail and session-less partial replay", async () => {
  await withAPI(async (requests) => {
    assert.match(
      renderToStaticMarkup(await RacePage(props())),
      /Australian Grand Prix/,
    );
    const html = renderToStaticMarkup(await ReplayPage(props()));
    assert.match(html, /Partial \/ approximate replay/);
    assert.match(html, /Recorded order replay/);
    assert.match(html, />Play<\/button>/);
    assert.match(html, /Norris/);
    assert.match(html, new RegExp(`season=2025&amp;session=${raceId}`));
    assert.equal(
      requests.filter((path) => path === `sessions/${raceId}/replay`).length,
      1,
    );
    assert.ok(!requests.includes(`sessions/${qualifyingId}/replay`));
  });
});
test("missing season-list entry does not turn an existing event into not-found", async () => {
  await withAPI(
    async () => {
      assert.match(
        renderToStaticMarkup(await RacePage(props())),
        /Australian Grand Prix/,
      );
      assert.match(renderToStaticMarkup(await ReplayPage(props())), /Norris/);
    },
    { seasons: [] },
  );
});
test("explicit API unavailability renders a grounded empty state, never not-found", async () => {
  await withAPI(
    async () => {
      const html = renderToStaticMarkup(
        await ReplayPage(props({ season: "2025", session: raceId })),
      );
      assert.match(html, /Replay unavailable/);
      assert.doesNotMatch(html, />Play<\/button>/);
    },
    { capability: "unavailable" },
  );
});
test("a missing event uses the same not-found boundary on both routes", async () => {
  await withAPI(async () => {
    await assert.rejects(
      RacePage(props({ season: "2025" }, missingId)),
      /notFound/,
    );
    await assert.rejects(
      ReplayPage(props({ season: "2025" }, missingId)),
      /notFound/,
    );
    const { default: NotFound } = component("not-found.tsx", {
      "next/link": link,
    });
    assert.match(
      renderToStaticMarkup(createElement(NotFound)),
      /This page is unavailable/,
    );
  });
});
test("foreign session and conflicting known season remain rejected", async () => {
  await withAPI(async () => {
    await assert.rejects(ReplayPage(props({ season: "2010" })), /notFound/);
    await assert.rejects(
      ReplayPage(props({ season: "2025", session: missingId })),
      /notFound/,
    );
  });
});
test("race actions are distinct links and replay never submits or targets Pitwall", async () => {
  await withAPI(async () => {
    // A qualifying tab must still offer the weekend's recorded race replay.
    const html = renderToStaticMarkup(
      await RacePage(props({ season: "2025", session: qualifyingId })),
    );
    const actions = html.match(
      /<nav[^>]*aria-label="Race weekend actions"[^>]*>(.*?)<\/nav>/s,
    )?.[1];
    assert.ok(actions, "actions have their own spaced navigation region");
    const links = [
      ...actions.matchAll(/<a[^>]*href="([^"]*)"[^>]*>(.*?)<\/a>/g),
    ];
    assert.equal(links.length, 3);
    assert.deepEqual(
      links.map((row) => row[2]),
      [
        "Ask Pitwall about this weekend",
        "Open race replay",
        "Explore race strategy and tyres",
      ],
    );
    assert.equal(links[0][1], "#pitwall");
    assert.equal(
      links[1][1],
      `/races/${eventId}/replay?season=2025&amp;session=${raceId}`,
    );
    assert.equal(links[2][1], `/strategy?season=2025&amp;event=${eventId}`);
    assert.doesNotMatch(actions, /<form|<button|question=|ai\/query|onClick/);
  });
});

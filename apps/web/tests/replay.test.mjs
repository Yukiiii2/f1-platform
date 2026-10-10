import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import * as replay from "../app/_lib/replay.ts";
import * as formatting from "../app/_lib/format.ts";

const driver = {
  driver: { id: "a", code: "NOR", given_name: "Lando", family_name: "Norris" },
  team: null,
  positions: [
    { elapsed_seconds: 10, position: 2 },
    { elapsed_seconds: 80, position: 1 },
  ],
  intervals: [],
  laps: [
    { lap_number: 2, start_seconds: 10, end_seconds: 30, approximate: true },
  ],
  pits: [{ elapsed_seconds: 15, lane_duration_seconds: "5", lap_number: 2 }],
};
const payload = {
  capability: "partial",
  provisional: false,
  duration_seconds: 90,
  drivers: [driver],
  race_control: [],
  quality: { max_hold_seconds: 30, notes: [] },
};

test("order is never taken from future samples or interpolated across a gap", () => {
  assert.equal(replay.driverAt(driver, 0, 30).position, null);
  assert.equal(replay.driverAt(driver, 10, 30).quality, "source");
  assert.equal(replay.driverAt(driver, 20, 30).position, 2);
  assert.equal(replay.driverAt(driver, 20, 30).quality, "held");
  assert.equal(replay.driverAt(driver, 41, 30).position, null);
  assert.equal(replay.driverAt(driver, 41, 30).quality, "unavailable");
  assert.equal(replay.driverAt(driver, 80, 30).position, 1);
});
test("lap windows stay estimated and pit activity needs recorded duration", () => {
  assert.equal(replay.driverAt(driver, 20, 30).lap.approximate, true);
  assert.equal(replay.driverAt(driver, 31, 30).lap, null);
  assert.equal(replay.driverAt(driver, 16, 30).inPit, true);
  assert.equal(replay.driverAt(driver, 21, 30).inPit, null);
  assert.equal(
    replay.driverAt(
      {
        ...driver,
        pits: [{ elapsed_seconds: 15, lane_duration_seconds: null }],
      },
      16,
      30,
    ).inPit,
    null,
  );
});
test("playback starts paused; play/pause, scrub, restart and speeds are bounded", () => {
  let state = replay.initialPlayback(payload);
  assert.equal(state.playing, false);
  state = replay.reducePlayback(state, { type: "play" }, 90);
  state = replay.reducePlayback(state, { type: "tick", seconds: 2 }, 90);
  assert.equal(state.elapsed, 2);
  state = replay.reducePlayback(state, { type: "speed", speed: 4 }, 90);
  state = replay.reducePlayback(state, { type: "tick", seconds: 2 }, 90);
  assert.equal(state.elapsed, 10);
  state = replay.reducePlayback(state, { type: "pause" }, 90);
  assert.equal(
    replay.reducePlayback(state, { type: "tick", seconds: 2 }, 90).elapsed,
    10,
  );
  state = replay.reducePlayback(state, { type: "scrub", elapsed: 100 }, 90);
  assert.equal(state.elapsed, 90);
  assert.equal(state.playing, false);
  state = replay.reducePlayback(state, { type: "restart" }, 90);
  assert.equal(state.elapsed, 0);
  assert.equal(state.playing, false);
});
test("driver selection and focus never hide or focus a disabled driver silently", () => {
  let state = replay.initialPlayback(payload);
  state = replay.reducePlayback(state, { type: "focus", id: "a" }, 90);
  assert.equal(state.focus, "a");
  state = replay.reducePlayback(state, { type: "toggle", id: "a" }, 90);
  assert.equal(state.visible.length, 0);
  assert.equal(state.focus, null);
  state = replay.reducePlayback(state, { type: "focus", id: "a" }, 90);
  assert.deepEqual(state.visible, ["a"]);
  assert.equal(state.focus, "a");
});
test("replay URL preserves the actual event, season and session deterministically", () => {
  assert.equal(
    replay.replayHref("event", 2010, "session"),
    "/races/event/replay?season=2010&session=session",
  );
});
test("accessible controls render paused without autoplay or coordinate claims", () => {
  const require = createRequire(import.meta.url);
  const source = readFileSync(
    new URL("../app/_components/race-replay.tsx", import.meta.url),
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
    (name) => (name === "../_lib/replay" ? replay : require(name)),
    module,
    module.exports,
  );
  const html = renderToStaticMarkup(
    createElement(module.exports.RaceReplay, { replay: payload }),
  );
  for (const label of [
    "Play",
    "Restart",
    "Replay time",
    "Playback speed",
    "Show Norris",
    "Focus Norris",
    "0.5",
    "4",
  ])
    assert.ok(html.includes(label), label);
  assert.match(html, /type="range"/);
  assert.match(html, /type="checkbox"/);
  assert.match(html, /Unavailable/);
  assert.doesNotMatch(html, /autoplay|Pause|latitude|longitude|GPS/);
});

function loadComponent(path, stubs = {}) {
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
    (name) => stubs[name] ?? require(name),
    module,
    module.exports,
  );
  return module.exports;
}
test("historical replay route preserves context and shows unavailable without creating markers", async () => {
  const event = { id: "event", name: "Australian GP", season_id: "year" };
  const session = { id: "session", type: "race" };
  const stop = () => {
    throw new Error("notFound");
  };
  let requests = 0,
    pitwallContext;
  const sharedData = loadComponent("_lib/data.ts", {
    "next/navigation": { notFound: stop },
    "./format": formatting,
    "./api": {
      getEntity: async () => event,
      getList: async (path) =>
        path === "seasons" ? [{ id: "year", year: 2010 }] : [session],
    },
  });
  const { default: Page } = loadComponent("races/[eventId]/replay/page.tsx", {
    "next/link": {
      default: ({ prefetch, children, ...props }) =>
        createElement("a", props, children),
    },
    "next/navigation": {
      notFound: stop,
      redirect: (url) => {
        throw new Error(url);
      },
    },
    "../../../_components/ui": {
      PageHeading: ({ title, children }) =>
        createElement("header", null, title, children),
      SeasonSelector: () => null,
      EmptyState: ({ title, children }) =>
        createElement("section", null, title, children),
    },
    "../../../_components/session-updates": { SessionUpdates: () => null },
    "../../../_components/race-replay": {
      RaceReplay: () => createElement("div", null, "PLAYBACK"),
    },
    "../../../_components/pitwall": {
      Pitwall: ({ context }) => {
        pitwallContext = context;
        return null;
      },
    },
    "../../../_lib/pitwall": { suggestedQuestions: () => [] },
    "../../../_lib/data": sharedData,
    "../../../_lib/api": {
      getList: async () => [{ id: "year", year: 2010 }],
      getSessionReplay: async (id) => {
        requests++;
        assert.equal(id, "session");
        return { ...payload, capability: "unavailable", session };
      },
    },
    "../../../_lib/contracts": { sessionNames: { race: "Race" } },
    "../../../_lib/replay": replay,
    "../../../_lib/format": formatting,
    "./replay.css": {},
  });
  const props = (query) => ({
    params: Promise.resolve({ eventId: "event" }),
    searchParams: Promise.resolve(query),
  });
  const html = renderToStaticMarkup(
    await Page(props({ season: "2010", session: "session" })),
  );
  assert.match(html, /Replay unavailable/);
  assert.match(html, /Historical results alone cannot provide replay/);
  assert.match(html, /season=2010&amp;session=session/);
  assert.doesNotMatch(html, /PLAYBACK/);
  assert.equal(requests, 1);
  assert.deepEqual(pitwallContext, {
    route: "/races/event",
    event_id: "event",
    season: 2010,
    session_id: "session",
  });
  await assert.rejects(
    Page(props({ season: "2025", session: "session" })),
    /notFound/,
  );
  await assert.rejects(
    Page(props({ season: "2010", session: "foreign" })),
    /notFound/,
  );
  assert.match(
    renderToStaticMarkup(await Page(props({}))),
    /Replay unavailable/,
  );
  assert.equal(requests, 2);
});
test("replay fetch failure and loading boundaries offer an accessible retry", () => {
  const { default: ErrorPage } = loadComponent(
    "races/[eventId]/replay/error.tsx",
  );
  const html = renderToStaticMarkup(
    createElement(ErrorPage, { reset: () => {} }),
  );
  assert.match(html, /role="alert"/);
  assert.match(html, /Retry replay/);
  assert.doesNotMatch(html, /OpenF1|Gemini|API|503|quota/);
  const { default: Loading } = loadComponent(
    "races/[eventId]/replay/loading.tsx",
  );
  assert.match(renderToStaticMarkup(createElement(Loading)), /role="status"/);
});

test("rendered playback, scrub, speed and driver controls dispatch the actual actions", () => {
  const require = createRequire(import.meta.url);
  let current;
  const { RaceReplay } = loadComponent("_components/race-replay.tsx", {
    "../_lib/replay": replay,
    react: {
      ...require("react"),
      useEffect: () => {},
      useMemo: (compute) => compute(),
      useReducer: (reduce, input, initialize) => {
        current ??= initialize(input);
        return [
          current,
          (action) => {
            current = reduce(current, action);
          },
        ];
      },
    },
  });
  function elements(tree) {
    if (Array.isArray(tree)) return tree.flatMap(elements);
    if (!tree || typeof tree !== "object") return [];
    return [tree, ...elements(tree.props?.children)];
  }
  const render = () => elements(RaceReplay({ replay: payload }));
  let tree = render();
  tree
    .find((row) => row.type === "button" && row.props.children === "Play")
    .props.onClick();
  assert.ok(
    render().some(
      (row) => row.type === "button" && row.props.children === "Pause",
    ),
  );
  tree = render();
  tree
    .find((row) => row.type === "button" && row.props.children === "Pause")
    .props.onClick();
  tree
    .find((row) => row.type === "input" && row.props.type === "range")
    .props.onChange({ target: { value: "55" } });
  assert.equal(
    render().find((row) => row.type === "input" && row.props.type === "range")
      .props.value,
    55,
  );
  render()
    .find((row) => row.type === "select" && row.props.value === 1)
    .props.onChange({ target: { value: "4" } });
  assert.ok(
    render().some((row) => row.type === "select" && row.props.value === 4),
  );
  render()
    .find((row) => row.type === "input" && row.props.type === "checkbox")
    .props.onChange();
  assert.equal(
    render().filter(
      (row) =>
        row.type === "li" && row.props.className?.startsWith("replay-row"),
    ).length,
    0,
  );
  render()
    .find((row) => row.type === "select" && row.props.value === "")
    .props.onChange({ target: { value: "a" } });
  assert.ok(
    render().some(
      (row) =>
        row.type === "li" &&
        row.props.className === "replay-row replay-row-focus",
    ),
  );
  render()
    .find((row) => row.type === "button" && row.props.children === "Restart")
    .props.onClick();
  assert.equal(current.elapsed, 0);
  assert.equal(current.playing, false);
});

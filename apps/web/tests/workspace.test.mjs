import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import * as api from "../app/_lib/api.ts";
import * as auth from "../app/_lib/auth.ts";

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
    createElement("header", {}, createElement("h1", {}, title), intro),
  EmptyState: ({ title, children }) =>
    createElement("section", {}, createElement("h2", {}, title), children),
};
const collection = {
  id: "11111111-1111-1111-1111-111111111111",
  title: "Wet race notes",
  description: "Recorded material",
  item_count: 1,
  created_at: "2026-10-11T00:00:00Z",
  updated_at: "2026-10-11T00:00:00Z",
};
const favorite = {
  id: "22222222-2222-2222-2222-222222222222",
  reference_type: "driver",
  reference_id: "33333333-3333-3333-3333-333333333333",
  season: 2025,
  label: "Lando Norris",
  open_url: "/drivers/33333333-3333-3333-3333-333333333333?season=2025",
  availability: "available",
  notices: [],
  created_at: collection.created_at,
  updated_at: collection.updated_at,
};

test("workspace authenticates before private reads and renders owner-only bounded lists", async () => {
  let user = null;
  const paths = [];
  const Page = load("workspace/page.tsx", {
    "next/link": link,
    "../_lib/auth": auth,
    "../_lib/auth-api": {
      accountState: async () => ({ user }),
      sessionHeaders: async () => ({}),
    },
    "../_components/sign-in-required": {
      SignInRequired: ({ next }) =>
        createElement("a", { href: auth.authHref("sign-in", next) }, "Sign in"),
    },
    "../_components/ui": ui,
    "./workspace-controls": {
      CreateCollection: () => createElement("button", {}, "Create collection"),
      ReferenceList: ({ rows }) =>
        createElement(
          "ul",
          {},
          rows.map((r) => createElement("li", { key: r.id }, r.label)),
        ),
    },
    "./workspace.css": {},
    "../_lib/workspace": {
      ...load("_lib/workspace.ts"),
      workspaceDate: (v) => v,
    },
    "../_lib/api": {
      ...api,
      workspaceRequest: async (path) => {
        paths.push(path);
        return path === "collections"
          ? [collection]
          : path === "favorites"
            ? [favorite]
            : [];
      },
      getComparisonPage: async () => [],
    },
  }).default;
  const props = { searchParams: Promise.resolve({ season: "2025" }) };
  assert.match(renderToStaticMarkup(await Page(props)), /Sign in/);
  assert.deepEqual(paths, []);
  user = { id: "owner", username: "race-reader" };
  const html = renderToStaticMarkup(await Page(props));
  for (const text of [
    "Workspace",
    "Saved comparisons",
    "Collections",
    "Favorite drivers",
    "Favorite race weekends",
    "Wet race notes",
    "Lando Norris",
    "Create collection",
  ])
    assert.ok(html.includes(text), text);
  assert.ok(html.includes("/collections/" + collection.id));
});

test("collection detail shows missing reference explicitly, preserves original context and handles private 404", async () => {
  let status;
  let recordedPath;
  const Detail = load("collections/[collectionId]/page.tsx", {
    "next/link": link,
    "next/navigation": {
      notFound: () => {
        throw new Error("not-found");
      },
    },
    "../../_lib/api": {
      ...api,
      workspaceRequest: async (path) => {
        recordedPath = path;
        if (status) throw new api.ApiError(status);
        return {
          ...collection,
          items: [
            {
              ...favorite,
              availability: "unavailable",
              open_url: null,
              label: "Reference unavailable",
              notices: [
                "Referenced record unavailable. No replacement was selected.",
              ],
            },
          ],
        };
      },
    },
    "../../_lib/auth-api": {
      accountState: async () => ({ user: { id: "owner" } }),
      sessionHeaders: async () => ({}),
    },
    "../../_components/sign-in-required": {},
    "../../_components/ui": ui,
    "../../workspace/workspace-controls": {
      EditCollection: () => createElement("button", {}, "Edit collection"),
      ReferenceList: ({ rows }) =>
        createElement(
          "div",
          {},
          rows[0].label,
          rows[0].notices[0],
          rows[0].open_url
            ? createElement("a", { href: rows[0].open_url }, "Open")
            : null,
        ),
    },
    "../../workspace/workspace.css": {},
  }).default;
  const props = {
    params: Promise.resolve({ collectionId: collection.id }),
    searchParams: Promise.resolve({ season: "2025" }),
  };
  const html = renderToStaticMarkup(await Detail(props));
  assert.equal(recordedPath, "collections/" + collection.id);
  assert.match(html, /Reference unavailable/);
  assert.match(html, /No replacement/);
  assert.ok(!html.includes(favorite.open_url));
  status = 404;
  await assert.rejects(Detail(props), /not-found/);
  status = 503;
  assert.match(
    renderToStaticMarkup(await Detail(props)),
    /temporarily unavailable/,
  );
});

test("workspace mutations route through authenticated transport and sanitize errors", async () => {
  const calls = [];
  let status;
  const Actions = load("workspace/actions.ts", {
    "../_lib/api": {
      ...api,
      workspaceRequest: async (...args) => {
        calls.push(args);
        if (status) throw new api.ApiError(status);
        return collection;
      },
    },
    "../_lib/auth-api": {
      sessionHeaders: async () => ({
        "X-F1-Auth": "1",
        Cookie: "private-session",
      }),
    },
    "../_lib/workspace": load("_lib/workspace.ts"),
  });
  assert.ok(
    (await Actions.mutateWorkspace("create", { title: "Notes" })).success,
  );
  await Actions.mutateWorkspace("add", {
    id: collection.id,
    reference: {
      reference_type: "comparison",
      reference_id: favorite.reference_id,
      season: 2025,
    },
  });
  await Actions.mutateWorkspace("favorite", {
    reference: {
      reference_type: "driver",
      reference_id: favorite.reference_id,
      season: 2025,
    },
  });
  await Actions.mutateWorkspace("unfavorite", { id: favorite.id });
  assert.equal(calls[1][0], `collections/${collection.id}/items`);
  assert.equal(calls[2][0], "favorites");
  assert.equal(calls[3][1], "DELETE");
  status = 401;
  const failure = await Actions.mutateWorkspace("delete", {
    id: collection.id,
  });
  assert.equal(failure.signInRequired, true);
  assert.ok(!JSON.stringify(failure).includes("private-session"));
  status = 429;
  assert.match(
    (await Actions.mutateWorkspace("delete", { id: collection.id })).error,
    /Wait/,
  );
  status = 503;
  const uncertain = await Actions.mutateWorkspace("delete", {
    id: collection.id,
  });
  assert.match(uncertain.error, /check whether your change was saved/i);
  assert.doesNotMatch(uncertain.error, /not been changed/);
  assert.match(
    (await Actions.mutateWorkspace("delete", { id: collection.id })).error,
    /temporarily unavailable/,
  );
});

test("public reference actions gate saves without gating race/driver reads and show favorite state", async () => {
  let user = null;
  const Actions = load("_components/reference-actions.tsx", {
    "next/link": link,
    "../_lib/auth": auth,
    "../_lib/auth-api": {
      accountState: async () => ({ user }),
      sessionHeaders: async () => ({}),
    },
    "../_lib/api": { ...api, workspaceRequest: async () => [favorite] },
    "./reference-controls": {
      ReferenceControls: ({ initialFavorite }) =>
        createElement(
          "button",
          {},
          initialFavorite ? "Unfavorite driver" : "Favorite driver",
        ),
    },
  }).ReferenceActions;
  const props = {
    reference: {
      reference_type: "driver",
      reference_id: favorite.reference_id,
      season: 2025,
    },
    returnTo: favorite.open_url,
  };
  const anonymous = renderToStaticMarkup(await Actions(props));
  assert.match(anonymous, /Sign in/);
  assert.ok(anonymous.includes(encodeURIComponent(favorite.open_url)));
  user = { id: "owner" };
  assert.match(renderToStaticMarkup(await Actions(props)), /Unfavorite driver/);
});

test("workspace and collection return URLs retain season and disallow external redirects", () => {
  assert.equal(
    auth.safeReturnTo("/workspace?season=2025"),
    "/workspace?season=2025",
  );
  assert.equal(
    auth.safeReturnTo("/collections/" + collection.id + "?season=2025"),
    "/collections/" + collection.id + "?season=2025",
  );
  assert.equal(
    auth.safeReturnTo("//outside.invalid/workspace"),
    "/comparisons",
  );
});

test("signed-in account navigation exposes Workspace without gating public navigation", () => {
  const Controls = load("_components/account-controls.tsx", {
    "next/link": link,
    "next/navigation": {
      useRouter: () => ({}),
      usePathname: () => "/races",
      useSearchParams: () => new URLSearchParams("season=2025"),
    },
    "../auth/actions": {},
    "../_lib/auth": auth,
  }).AccountControls;
  const signedIn = renderToStaticMarkup(
    createElement(Controls, { user: { id: "owner", username: "reader" } }),
  );
  assert.match(signedIn, /href="\/workspace\?season=2025"/);
  assert.match(signedIn, /Account/);
  assert.match(signedIn, /Sign out/);
  const signedOut = renderToStaticMarkup(
    createElement(Controls, { user: null }),
  );
  assert.match(signedOut, /Sign in/);
  assert.ok(!signedOut.includes("Workspace"));
});

function find(tree, predicate) {
  if (!tree || typeof tree !== "object") return null;
  if (predicate(tree)) return tree;
  for (const child of [tree.props?.children].flat(Infinity)) {
    const found = find(child, predicate);
    if (found) return found;
  }
  return null;
}
function interactionRuntime() {
  const states = [],
    pending = [];
  let cursor = 0;
  return {
    hooks: {
      useId: () => "test-control",
      useState: (initial) => {
        const index = cursor++;
        if (states[index] === undefined) states[index] = initial;
        return [
          states[index],
          (value) => {
            states[index] =
              typeof value === "function" ? value(states[index]) : value;
          },
        ];
      },
      useTransition: () => [false, (fn) => pending.push(fn())],
    },
    render: (fn) => {
      cursor = 0;
      return fn();
    },
    flush: async () => {
      await Promise.all(pending.splice(0));
    },
  };
}
test("favorites and collection picker submit exact references and preserve failed state", async () => {
  const runtime = interactionRuntime();
  const calls = [];
  let failure = false;
  const Controls = load("_components/reference-controls.tsx", {
    react: runtime.hooks,
    "next/link": link,
    "next/navigation": { useRouter: () => ({ refresh() {} }) },
    "../_lib/auth": auth,
    "../_lib/workspace": load("_lib/workspace.ts"),
    "../workspace/workspace.css": {},
    "../workspace/actions": {
      collectionOptions: async () => ({ rows: [collection] }),
      mutateWorkspace: async (...args) => {
        calls.push(args);
        return failure
          ? { error: "Temporarily unavailable" }
          : { success: true, response: favorite };
      },
    },
  });
  const reference = {
    reference_type: "driver",
    reference_id: favorite.reference_id,
    season: 2025,
  };
  const render = () =>
    runtime.render(() =>
      Controls.ReferenceControls({ reference, returnTo: favorite.open_url }),
    );
  find(render(), (n) => n.type === "button").props.onClick();
  await runtime.flush();
  assert.deepEqual(calls[0], ["favorite", { reference }]);
  assert.equal(
    find(render(), (n) => n.type === "button").props["aria-pressed"],
    true,
  );
  find(render(), (n) => n.type === "button").props.onClick();
  await runtime.flush();
  assert.deepEqual(calls[1], ["unfavorite", { id: favorite.id }]);
  // A fresh hook runtime models the picker component's independent state.
  const pickerRuntime = interactionRuntime();
  const Picker = load("_components/reference-controls.tsx", {
    react: pickerRuntime.hooks,
    "next/link": link,
    "next/navigation": {},
    "../_lib/auth": auth,
    "../_lib/workspace": load("_lib/workspace.ts"),
    "../workspace/workspace.css": {},
    "../workspace/actions": {
      collectionOptions: async () => ({ rows: [collection] }),
      mutateWorkspace: async (...args) => {
        calls.push(args);
        return { error: "Temporarily unavailable" };
      },
    },
  }).AddToCollection;
  const picker = () =>
    pickerRuntime.render(() =>
      Picker({ reference, returnTo: favorite.open_url }),
    );
  picker().props.onToggle({ currentTarget: { open: true } });
  await pickerRuntime.flush();
  const oldFormData = globalThis.FormData;
  globalThis.FormData = class {
    get() {
      return collection.id;
    }
  };
  try {
    find(picker(), (n) => n.type === "form").props.onSubmit({
      preventDefault() {},
      currentTarget: {},
    });
    await pickerRuntime.flush();
    assert.deepEqual(calls[2], ["add", { id: collection.id, reference }]);
    const tree = picker();
    assert.ok(find(tree, (n) => n.type === "select"));
    assert.equal(
      find(tree, (n) => n.props?.result?.error).props.result.error,
      "Temporarily unavailable",
    );
  } finally {
    globalThis.FormData = oldFormData;
  }
});

test("collection creation, editing, removal and confirmed deletion invoke their actions", async () => {
  const calls = [],
    navigation = [];
  const router = {
    push: (url) => navigation.push(url),
    replace: (url) => navigation.push(url),
    refresh() {},
  };
  const deps = (runtime) => ({
    react: runtime.hooks,
    "next/link": link,
    "next/navigation": { useRouter: () => router },
    "../_lib/workspace": load("_lib/workspace.ts"),
    "../_components/reference-controls": { WorkspaceFeedback: () => null },
    "./actions": {
      mutateWorkspace: async (...args) => {
        calls.push(args);
        return { success: true, response: collection };
      },
    },
  });
  const old = globalThis.FormData;
  globalThis.FormData = class {
    constructor(form) {
      this.form = form;
    }
    get(key) {
      return this.form[key];
    }
  };
  try {
    const createRuntime = interactionRuntime();
    const Create = load(
      "workspace/workspace-controls.tsx",
      deps(createRuntime),
    ).CreateCollection;
    find(
      createRuntime.render(() =>
        Create({ returnTo: "/workspace?season=2025&collections=50" }),
      ),
      (n) => n.type === "form",
    ).props.onSubmit({
      preventDefault() {},
      currentTarget: { title: "Title", description: "Description", reset() {} },
    });
    await createRuntime.flush();
    assert.deepEqual(calls[0], [
      "create",
      { title: "Title", description: "Description" },
    ]);
    assert.ok(navigation.includes(`/collections/${collection.id}?season=2025`));
    const editRuntime = interactionRuntime();
    const Edit = load(
      "workspace/workspace-controls.tsx",
      deps(editRuntime),
    ).EditCollection;
    const returnTo = `/collections/${collection.id}?season=2025&offset=50`;
    const render = () =>
      editRuntime.render(() => Edit({ collection, returnTo }));
    assert.equal(
      find(render(), (n) => n.props?.returnTo)?.props.returnTo,
      returnTo,
    );
    find(render(), (n) => n.type === "form").props.onSubmit({
      preventDefault() {},
      currentTarget: { title: "Renamed", description: "Changed" },
    });
    await editRuntime.flush();
    assert.deepEqual(calls[1], [
      "update",
      { id: collection.id, title: "Renamed", description: "Changed" },
    ]);
    find(
      render(),
      (n) => n.type === "button" && n.props.children === "Delete collection",
    ).props.onClick();
    assert.equal(calls.length, 2);
    find(
      render(),
      (n) => n.type === "button" && n.props.children === "Confirm delete",
    ).props.onClick();
    await editRuntime.flush();
    assert.deepEqual(calls[2], ["delete", { id: collection.id }]);
    assert.ok(navigation.includes("/workspace?season=2025"));
    const listRuntime = interactionRuntime();
    const List = load(
      "workspace/workspace-controls.tsx",
      deps(listRuntime),
    ).ReferenceList;
    find(
      listRuntime.render(() =>
        List({ rows: [favorite], collectionId: collection.id }),
      ),
      (n) => n.type === "button",
    ).props.onClick();
    await listRuntime.flush();
    assert.deepEqual(calls[3], [
      "remove",
      { id: collection.id, item_id: favorite.id },
    ]);
  } finally {
    globalThis.FormData = old;
  }
});

test("saved comparisons expose Add to collection with the exact saved identity and year", () => {
  const received = [];
  const Manage = load("comparisons/manage-comparisons.tsx", {
    "next/link": link,
    "next/navigation": { useRouter: () => ({}) },
    "./actions": {},
    "../_lib/saved-comparisons": {},
    "../_components/reference-controls": {
      AddToCollection: (props) => {
        received.push(props.reference);
        return createElement("button", {}, "Add to collection");
      },
    },
  }).ManageComparisons;
  const saved = {
    ...collection,
    comparison_type: "telemetry_laps",
    configuration: { season: 2025 },
    event_name: "Australian GP",
    session_name: "Race",
    driver_a_name: "Norris",
    driver_b_name: "Verstappen",
    lap_a_number: 4,
    lap_b_number: 5,
    availability: "partial",
    notices: [],
    open_url: "/telemetry?season=2025",
  };
  assert.match(
    renderToStaticMarkup(createElement(Manage, { rows: [saved] })),
    /Add to collection/,
  );
  assert.deepEqual(received, [
    { reference_type: "comparison", reference_id: saved.id, season: 2025 },
  ]);
});

test("driver profile remains public and passes selected season to private save actions", async () => {
  const referenceProps = [];
  const DriverPage = load("drivers/[driverId]/page.tsx", {
    "next/link": link,
    "../../_components/pitwall": { Pitwall: () => null },
    "../../_components/reference-actions": {
      ReferenceActions: (props) => {
        referenceProps.push(props);
        return createElement(
          "a",
          { href: auth.authHref("sign-in", props.returnTo) },
          "Sign in to save",
        );
      },
    },
    "../../_lib/pitwall": { suggestedQuestions: () => [] },
    "../../_lib/contracts": { sessionNames: {} },
    "../../_lib/format": {
      driverName: (d) => `${d.given_name} ${d.family_name}`,
      single: (v) => v,
    },
    "../../_components/ui": {
      ...ui,
      SeasonSelector: () => null,
      NoSeason: () => null,
      SectionHeading: ({ title }) => createElement("h2", {}, title),
    },
    "../../_lib/data": {
      detail: async () => ({
        id: favorite.reference_id,
        given_name: "Lando",
        family_name: "Norris",
      }),
      seasonContext: async () => ({
        seasons: [{ year: 2025 }],
        season: { year: 2025 },
      }),
      driverStandings: async () => [],
      seasonEvents: async () => [],
      references: async () => new Map(),
    },
  }).default;
  const html = renderToStaticMarkup(
    await DriverPage({
      params: Promise.resolve({ driverId: favorite.reference_id }),
      searchParams: Promise.resolve({ season: "2025" }),
    }),
  );
  assert.match(html, /Lando Norris/);
  assert.match(html, /No driver results/);
  assert.deepEqual(referenceProps[0].reference, {
    reference_type: "driver",
    reference_id: favorite.reference_id,
    season: 2025,
  });
});

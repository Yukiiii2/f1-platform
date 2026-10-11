import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import { safeReturnTo, authHref, authError } from "../app/_lib/auth.ts";
import * as api from "../app/_lib/api.ts";

function load(path, dependencies) {
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

test("sign-in return URLs keep exact analysis selectors and reject external/control redirects", () => {
  const selected =
    "/telemetry?season=2025&session=session&driver_a=a&driver_b=b&lap_a=1&lap_b=2&alignment=elapsed_time&compare=1";
  assert.equal(safeReturnTo(selected), selected);
  assert.equal(safeReturnTo("/?season=2010"), "/?season=2010");
  assert.equal(
    new URL(authHref("sign-in", selected), "http://test").searchParams.get(
      "next",
    ),
    selected,
  );
  for (const bad of [
    "https://evil.test",
    "//evil.test",
    "/\\evil",
    "/%2f%2fevil",
    "/sign-in",
    "/telemetry\nLocation:evil",
  ])
    assert.equal(safeReturnTo(bad), "/comparisons");
});

test("opaque session transport forwards only the session and applies HttpOnly cookies server-side", async () => {
  const token = "a".repeat(43);
  const changes = [];
  const jar = {
    get: (name) =>
      name === "f1_session" ? { value: token } : { value: "unrelated-secret" },
    set: (...args) => changes.push(args),
    delete: (name) => changes.push([name, "deleted"]),
  };
  const authAPI = load("_lib/auth-api.ts", {
    "next/headers": {
      cookies: async () => jar,
      headers: async () => new Headers({ origin: "http://localhost:3000" }),
    },
    react: { cache: (fn) => fn },
    "./api": api,
  });
  const headers = await authAPI.sessionHeaders();
  assert.equal(headers.Cookie, `f1_session=${token}`);
  assert.equal(headers["X-F1-Auth"], "1");
  assert.ok(!JSON.stringify(headers).includes("unrelated-secret"));
  await authAPI.applySessionCookie(
    new Headers({
      "set-cookie": `f1_session=${token}; HttpOnly; Path=/; SameSite=lax; Max-Age=43200; Secure`,
    }),
  );
  assert.equal(changes[0][2].httpOnly, true);
  assert.equal(changes[0][2].secure, true);
  await assert.rejects(
    authAPI.applySessionCookie(
      new Headers({ "set-cookie": "f1_session=bad; Path=/" }),
    ),
    api.ApiError,
  );
});

test("authentication server actions return no credentials or tokens and sanitize failures", async () => {
  const calls = [];
  let failed = false;
  const actions = load("auth/actions.ts", {
    "../_lib/auth-api": {
      authFetch: async (path, body) => {
        calls.push([path, body]);
        if (failed) throw new api.ApiError(401);
        return new Response("{}", { headers: { "set-cookie": "server-only" } });
      },
      applySessionCookie: async () => {},
      clearSessionCookie: async () => {},
    },
    "../_lib/api": api,
    "../_lib/auth": { authError },
  });
  assert.deepEqual(
    await actions.authenticate("login", "driver-a", "private-password"),
    { success: true },
  );
  assert.equal(calls[0][0], "auth/login");
  failed = true;
  const failure = await actions.authenticate(
    "login",
    "driver-a",
    "private-password",
  );
  assert.ok(!JSON.stringify(failure).includes("private-password"));
  assert.match(failure.error, /sign-in name or password/i);
});

test("account forms and signed-in/sign-out state use labelled accessible controls", () => {
  const Form = load("auth/auth-form.tsx", {
    "next/link": link,
    "next/navigation": { useRouter: () => ({}) },
    "./actions": {},
    "../_lib/auth": { authHref, authError },
  }).AuthForm;
  const html = renderToStaticMarkup(
    createElement(Form, { mode: "register", next: "/strategy?season=2025" }),
  );
  assert.ok(html.includes("Create account"));
  assert.match(html, /autocomplete="username"/i);
  assert.match(html, /autocomplete="new-password"/i);
  assert.ok(html.includes('type="password"'));
  assert.ok(html.includes("Confirm password"));
  const Controls = load("_components/account-controls.tsx", {
    "next/link": link,
    "next/navigation": {
      usePathname: () => "/telemetry",
      useSearchParams: () => new URLSearchParams("season=2025"),
      useRouter: () => ({}),
    },
    "../auth/actions": {},
    "../_lib/auth": { authHref, authError },
  }).AccountControls;
  assert.ok(
    renderToStaticMarkup(
      createElement(Controls, { user: { id: "user", username: "driver-a" } }),
    ).includes("Sign out"),
  );
  assert.ok(
    renderToStaticMarkup(createElement(Controls, { user: null })).includes(
      "Sign in",
    ),
  );
});

test("logged-out save control preserves comparison URL and does not fabricate saved state", () => {
  const Save = load("_components/save-comparison.tsx", {
    "next/link": link,
    "../comparisons/actions": {},
    "../_lib/saved-comparisons": {},
    "../_lib/auth": { authHref },
  }).SaveComparison;
  const next = "/telemetry?season=2025&lap_a=one&lap_b=two&compare=1";
  const html = renderToStaticMarkup(
    createElement(Save, {
      preset: { configuration: { season: 2025 } },
      suggestedTitle: "Lap pair",
      signedIn: false,
      returnTo: next,
    }),
  );
  assert.ok(html.includes("Sign in to save"));
  assert.ok(html.includes(encodeURIComponent(next)));
  assert.ok(!html.includes('type="submit"'));
});

test("account lookup avoids anonymous requests and treats expired/unavailable sessions safely", async () => {
  let token;
  let status = 200;
  let calls = 0;
  const original = globalThis.fetch;
  const authAPI = load("_lib/auth-api.ts", {
    "next/headers": {
      cookies: async () => ({
        get: () => (token ? { value: token } : undefined),
      }),
      headers: async () => new Headers(),
    },
    react: { cache: (fn) => fn },
    "./api": api,
  });
  globalThis.fetch = async (_url, options) => {
    calls++;
    assert.equal(options.cache, "no-store");
    return new Response(
      JSON.stringify({
        id: "user-id",
        username: "driver-a",
        extra: "not-for-client",
      }),
      { status },
    );
  };
  try {
    assert.deepEqual(await authAPI.accountState(), { user: null });
    assert.equal(calls, 0);
    token = "a".repeat(43);
    assert.deepEqual(await authAPI.accountState(), {
      user: { id: "user-id", username: "driver-a" },
    });
    status = 401;
    assert.deepEqual(await authAPI.accountState(), { user: null });
    status = 503;
    assert.match(
      (await authAPI.accountState()).error,
      /temporarily unavailable/,
    );
  } finally {
    globalThis.fetch = original;
  }
});

test("logged-out saved list never fetches private records and expired open retains its return URL", async () => {
  const ui = {
    EmptyState: ({ title, children }) =>
      createElement("section", {}, title, children),
    PageHeading: () => null,
  };
  const Gate = load("_components/sign-in-required.tsx", {
    "next/link": link,
    "../_lib/auth": { authHref },
    "./ui": ui,
  }).SignInRequired;
  let reads = 0;
  const Page = load("comparisons/page.tsx", {
    "next/link": link,
    "../_lib/auth-api": {
      accountState: async () => ({ user: null }),
      sessionHeaders: async () => ({}),
    },
    "../_components/sign-in-required": { SignInRequired: Gate },
    "../_components/ui": ui,
    "../_lib/api": {
      ...api,
      getComparisonPage: async () => {
        reads++;
        return [];
      },
    },
    "../_lib/format": { single: (value) => value },
    "./manage-comparisons": {},
    "./comparisons.css": {},
  }).default;
  const html = renderToStaticMarkup(
    await Page({ searchParams: Promise.resolve({ season: "2010" }) }),
  );
  assert.match(html, /Sign in to use Saved Comparisons/);
  assert.equal(reads, 0);
  assert.ok(
    html.includes(encodeURIComponent("/comparisons?season=2010&offset=0")),
  );
  const Open = load("comparisons/[comparisonId]/open/page.tsx", {
    "next/link": link,
    "next/navigation": {},
    "../../../_lib/api": {
      ...api,
      getSavedComparison: async () => {
        throw new api.ApiError(401);
      },
    },
    "../../../_lib/auth-api": { sessionHeaders: async () => ({}) },
    "../../../_components/ui": ui,
    "../../../_components/sign-in-required": { SignInRequired: Gate },
  }).default;
  const opened = renderToStaticMarkup(
    await Open({ params: Promise.resolve({ comparisonId: "saved-id" }) }),
  );
  assert.ok(opened.includes(encodeURIComponent("/comparisons/saved-id/open")));
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
test("registration checks confirmation and successful sign-in restores selectors without exposing errors", async () => {
  const pending = [];
  let state;
  let resets = 0;
  const calls = [];
  const navigation = [];
  const next =
    "/strategy?season=2010&event=weekend&session=race&a=first&b=second";
  let result = { success: true };
  const Form = load("auth/auth-form.tsx", {
    react: {
      useId: () => "account",
      useState: () => [
        state,
        (value) => {
          state = value;
        },
      ],
      useTransition: () => [false, (action) => pending.push(action())],
    },
    "next/link": link,
    "next/navigation": {
      useRouter: () => ({
        replace: (url) => navigation.push(url),
        refresh: () => navigation.push("refresh"),
      }),
    },
    "./actions": {
      authenticate: async (...args) => {
        calls.push(args);
        return result;
      },
    },
    "../_lib/auth": { authHref, authError },
  }).AuthForm;
  const original = globalThis.FormData;
  globalThis.FormData = class {
    constructor(form) {
      this.form = form;
    }
    get(key) {
      return this.form[key];
    }
  };
  try {
    const form = {
      username: "driver-a",
      password: " exact-secret-password ",
      confirm: "incorrect",
      reset: () => resets++,
    };
    const submit = () =>
      find(
        Form({ mode: "register", next }),
        (node) => node.type === "form",
      ).props.onSubmit({ preventDefault() {}, currentTarget: form });
    submit();
    assert.equal(calls.length, 0);
    assert.match(state, /must match/);
    form.confirm = form.password;
    submit();
    await Promise.all(pending.splice(0));
    assert.deepEqual(calls[0], ["register", "driver-a", form.password]);
    assert.deepEqual(navigation, [next, "refresh"]);
    assert.equal(resets, 1);
    result = { error: authError(429) };
    submit();
    await Promise.all(pending.splice(0));
    assert.match(state, /Wait a moment/);
    assert.equal(resets, 1);
    assert.equal(navigation.length, 2);
  } finally {
    globalThis.FormData = original;
  }
});

test("logout clears the cookie and refreshes only after server revocation succeeds", async () => {
  let fail = false;
  let cleared = 0;
  let refresh = 0;
  const pending = [];
  const actions = load("auth/actions.ts", {
    "../_lib/api": api,
    "../_lib/auth": { authError },
    "../_lib/auth-api": {
      authFetch: async () => {
        if (fail) throw new api.ApiError(503);
        return new Response(null, { status: 204 });
      },
      clearSessionCookie: async () => cleared++,
      applySessionCookie: async () => {},
    },
  });
  const Controls = load("_components/account-controls.tsx", {
    react: {
      useState: () => [null, () => {}],
      useTransition: () => [false, (action) => pending.push(action())],
    },
    "next/link": link,
    "../auth/actions": actions,
    "../_lib/auth": { authHref, authError },
    "next/navigation": {
      usePathname: () => "/comparisons",
      useSearchParams: () => new URLSearchParams(),
      useRouter: () => ({ refresh: () => refresh++ }),
    },
  }).AccountControls;
  const click = () =>
    find(
      Controls({ user: { id: "user", username: "driver-a" } }),
      (node) => node.type === "button",
    ).props.onClick();
  click();
  await Promise.all(pending.splice(0));
  assert.equal(cleared, 1);
  assert.equal(refresh, 1);
  fail = true;
  click();
  await Promise.all(pending.splice(0));
  assert.equal(cleared, 1);
  assert.equal(refresh, 1);
});

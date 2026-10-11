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
const profile = {
  id: "user",
  username: "driver-a",
  created_at: "2026-10-11T00:00:00Z",
  updated_at: "2026-10-11T00:00:00Z",
  saved_comparison_count: 2,
  sessions: [
    {
      created_at: "2026-10-11T00:00:00Z",
      expires_at: "2026-10-11T12:00:00Z",
      is_current: true,
    },
    {
      created_at: "2026-10-10T22:00:00Z",
      expires_at: "2026-10-11T10:00:00Z",
      is_current: false,
    },
  ],
};

test("account renders current identity, saved count, safe session metadata and labelled settings", async () => {
  const Settings = load("account/account-settings.tsx", {
    "next/link": link,
    "next/navigation": { useRouter: () => ({}) },
    "./actions": {},
    "../_lib/auth": auth,
  }).AccountSettings;
  const Page = load("account/page.tsx", {
    "next/link": link,
    "../_lib/api": api,
    "../_lib/auth": auth,
    "../_lib/auth-api": {
      authFetch: async () => new Response(JSON.stringify(profile)),
    },
    "../_components/ui": ui,
    "./account-settings": { AccountSettings: Settings },
    "./account.css": {},
  }).default;
  const html = renderToStaticMarkup(await Page());
  for (const text of [
    "driver-a",
    "Saved comparisons",
    "2",
    "Current session",
    "Change sign-in name",
    "Change password",
    "Sign out other sessions",
    "Delete account",
    "Current password",
    "DELETE",
  ])
    assert.ok(html.includes(text), text);
  assert.match(html, /autocomplete="current-password"/i);
  assert.match(html, /autocomplete="new-password"/i);
  assert.ok(!html.includes("token_hash"));
});

test("account rejects anonymous visitors and fetch failure shows retry without private fields", async () => {
  let status = 401;
  const Page = load("account/page.tsx", {
    "next/link": link,
    "../_lib/api": api,
    "../_lib/auth": auth,
    "../_lib/auth-api": {
      authFetch: async () => {
        throw new api.ApiError(status);
      },
    },
    "../_components/ui": ui,
    "./account-settings": {},
    "./account.css": {},
  }).default;
  const html = renderToStaticMarkup(await Page());
  assert.match(html, /Sign in/);
  assert.ok(html.includes(encodeURIComponent("/account")));
  assert.ok(!html.includes("driver-a"));
  const seasonal = renderToStaticMarkup(
    await Page({ searchParams: Promise.resolve({ season: "2025" }) }),
  );
  assert.ok(seasonal.includes(encodeURIComponent("/account?season=2025")));
  status = 503;
  assert.match(renderToStaticMarkup(await Page()), /Retry/);
});

test("settings actions route through backend and rotate/clear cookies only after success", async () => {
  const calls = [];
  let rotated = 0;
  let cleared = 0;
  let status;
  const actions = load("account/actions.ts", {
    "../_lib/api": api,
    "../_lib/auth": auth,
    "../_lib/auth-api": {
      authFetch: async (...args) => {
        calls.push(args);
        if (status) throw new api.ApiError(status);
        return new Response(null, { status: 204 });
      },
      applySessionCookie: async () => rotated++,
      clearSessionCookie: async () => cleared++,
    },
  });
  assert.deepEqual(
    await actions.updateAccount("username", { username: "new-name" }),
    { success: true },
  );
  assert.deepEqual(calls[0], [
    "auth/username",
    { username: "new-name" },
    "PATCH",
  ]);
  await actions.updateAccount("password", {
    current_password: "private-current",
    new_password: "private-new-password",
  });
  assert.equal(rotated, 1);
  await actions.updateAccount("sessions", {});
  assert.equal(calls[2][0], "auth/sessions/revoke-others");
  status = 400;
  const failed = await actions.updateAccount("delete", {
    current_password: "private-current",
    confirmation: "DELETE",
  });
  assert.match(failed.error, /Current password/);
  assert.equal(cleared, 0);
  assert.ok(!JSON.stringify(failed).includes("private-current"));
  assert.equal(failed.signInRequired, undefined);
  status = 401;
  assert.deepEqual(await actions.updateAccount("sessions", {}), {
    error: auth.accountError(401),
    signInRequired: true,
  });
  status = undefined;
  await actions.updateAccount("delete", {
    current_password: "private-current",
    confirmation: "DELETE",
  });
  assert.equal(cleared, 1);
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
test("password confirmation and destructive confirmation gate submission; deletion redirects only on success", async () => {
  const pending = [];
  const calls = [];
  const navigation = [];
  let cursor = 0;
  let response = { success: true };
  const states = [];
  const Settings = load("account/account-settings.tsx", {
    react: {
      useId: () => "settings",
      useState: (initial) => {
        const i = cursor++;
        if (states[i] === undefined) states[i] = initial;
        return [
          states[i],
          (v) => {
            states[i] = v;
          },
        ];
      },
      useTransition: () => [false, (fn) => pending.push(fn())],
    },
    "next/link": link,
    "next/navigation": {
      useRouter: () => ({
        replace: (url) => navigation.push(url),
        refresh: () => navigation.push("refresh"),
      }),
    },
    "../_lib/auth": auth,
    "./actions": {
      updateAccount: async (...args) => {
        calls.push(args);
        return response;
      },
    },
  }).AccountSettings;
  const original = globalThis.FormData;
  globalThis.FormData = class {
    constructor(form) {
      this.form = form;
    }
    get(key) {
      return this.form[key];
    }
  };
  const submit = (kind, values) => {
    cursor = 0;
    const tree = Settings({ profile });
    return find(
      tree,
      (node) => node.type === "form" && node.props["data-setting"] === kind,
    ).props.onSubmit({
      preventDefault() {},
      currentTarget: { ...values, reset() {} },
    });
  };
  try {
    submit("password", {
      current_password: "old-secret",
      new_password: "new-secret-long",
      confirm_password: "different",
    });
    assert.equal(calls.length, 0);
    submit("password", {
      current_password: "old-secret",
      new_password: "new-secret-long",
      confirm_password: "new-secret-long",
    });
    await Promise.all(pending.splice(0));
    assert.equal(calls[0][0], "password");
    assert.equal(calls[0][1].current_password, "old-secret");
    submit("username", { username: "new-name" });
    submit("sessions", {});
    await Promise.all(pending.splice(0));
    assert.equal(calls[1][0], "username");
    assert.equal(calls[2][0], "sessions");
    submit("delete", { current_password: "old-secret", confirmation: "wrong" });
    assert.equal(calls.length, 3);
    response = { error: "Current password is incorrect." };
    submit("delete", {
      current_password: "wrong-secret",
      confirmation: "DELETE",
    });
    await Promise.all(pending.splice(0));
    assert.ok(!navigation.includes("/"));
    response = { success: true };
    submit("delete", {
      current_password: "old-secret",
      confirmation: "DELETE",
    });
    await Promise.all(pending.splice(0));
    assert.equal(calls[4][0], "delete");
    assert.ok(navigation.includes("/"));
  } finally {
    globalThis.FormData = original;
  }
});

test("account return context and signed-in navigation include account settings", () => {
  assert.equal(
    auth.safeReturnTo("/account?season=2025"),
    "/account?season=2025",
  );
  const Controls = load("_components/account-controls.tsx", {
    "next/link": link,
    "next/navigation": {
      useRouter: () => ({}),
      usePathname: () => "/account",
      useSearchParams: () => new URLSearchParams("season=2025"),
    },
    "../auth/actions": {},
    "../_lib/auth": auth,
  }).AccountControls;
  assert.match(
    renderToStaticMarkup(createElement(Controls, { user: profile })),
    /href="\/account\?season=2025"/,
  );
});

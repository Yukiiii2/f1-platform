import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
const require = createRequire(import.meta.url);
function component() {
  const { outputText } = ts.transpileModule(
    readFileSync(
      new URL("../app/_components/session-updates.tsx", import.meta.url),
      "utf8",
    ),
    {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        jsx: ts.JsxEmit.ReactJSX,
      },
    },
  );
  const module = { exports: {} };
  new Function("require", "module", "exports", outputText)(
    (name) =>
      name === "next/navigation"
        ? { useRouter: () => ({ refresh() {} }) }
        : require(name),
    module,
    module.exports,
  );
  return module.exports.SessionUpdates;
}
test("live source data is explicitly provisional with a manual refresh action", () => {
  const html = renderToStaticMarkup(
    createElement(component(), {
      session: {
        status: "in_progress",
        updates: {
          data_status: "provisional",
          live_active: true,
          live_suspended: false,
          live_updated_at: "2025-03-16T04:03:00Z",
        },
      },
    }),
  );
  assert.match(html, /Live session/);
  assert.doesNotMatch(html, /\uFFFD/);
  assert.match(html, /Provisional/);
  assert.match(html, /not a final classification/);
  assert.match(html, /Refresh session data/);
});
test("finalization pending and paused refresh stay provisional; completed records are labelled finalized", () => {
  const show = (status, data_status, live_suspended = false) =>
    renderToStaticMarkup(
      createElement(component(), {
        session: { status, updates: { data_status, live_suspended } },
      }),
    );
  assert.match(show("completed", "provisional"), /Final update pending/);
  assert.match(
    show("in_progress", "provisional", true),
    /temporarily unavailable/,
  );
  assert.match(show("completed", "finalized"), /Finalized session data/);
  assert.equal(show("unknown", "not_tracked"), "");
  assert.match(show("cancelled", "provisional"), /Session cancelled/);
  assert.doesNotMatch(
    show("cancelled", "provisional"),
    /Live session|updates pending/,
  );
});

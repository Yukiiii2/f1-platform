import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import ts from "typescript";
import React from "react";
import * as jsxRuntime from "react/jsx-runtime";
import { renderToStaticMarkup } from "react-dom/server";
import * as geometry from "../app/_lib/car-geometry.ts";

test("static fallback matches the authored geometry and renders without WebGL", () => {
  assert.equal(
    readFileSync(
      new URL("../public/illustrations/open-wheel-car.svg", import.meta.url),
      "utf8",
    ),
    geometry.carSvg(),
  );
  const source = readFileSync(
    new URL("../app/_components/car-showcase.tsx", import.meta.url),
    "utf8",
  );
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      jsx: ts.JsxEmit.ReactJSX,
      esModuleInterop: true,
    },
  });
  const module = { exports: {} };
  new Function("require", "module", "exports", outputText)(
    (name) => {
      if (name === "react") return React;
      if (name === "react/jsx-runtime") return jsxRuntime;
      if (name === "next/image")
        return ({ fill, unoptimized, ...props }) =>
          React.createElement("img", props);
      if (name.endsWith(".css")) return {};
      throw new Error(`Unexpected eager import: ${name}`);
    },
    module,
    module.exports,
  );
  const html = renderToStaticMarkup(
    React.createElement(module.exports.CarShowcase),
  );
  assert.match(html, /data-ready="false"/);
  assert.match(html, /Explore in 3D/);
  assert.match(html, /Authored geometry, not a team car or race replay/);
  assert.match(html, /alt="A stylized open-wheel/);
  assert.doesNotMatch(html, /type="range"/);
});

test("authored car geometry is finite, normalized and bounded for a lightweight scene", () => {
  const triangles = geometry.carGeometry();
  assert.ok(triangles.length > 100 && triangles.length * 3 < 6000);
  for (const triangle of triangles) {
    assert.equal(triangle.points.length, 3);
    assert.ok(triangle.points.flat().every(Number.isFinite));
    assert.ok(Math.abs(Math.hypot(...triangle.normal) - 1) < 0.00001);
    assert.ok(triangle.color.every((channel) => channel >= 0 && channel <= 1));
  }
  const before = structuredClone(triangles);
  for (const aspect of [1.5, 720 / 320, 3.6])
    for (const yaw of [
      -Math.PI,
      -Math.PI / 2,
      0,
      geometry.DEFAULT_YAW,
      Math.PI / 2,
      Math.PI,
    ]) {
      for (const triangle of triangles)
        for (const point of triangle.points) {
          const projected = geometry.project(point, yaw, aspect);
          assert.ok(projected.every(Number.isFinite));
          assert.ok(Math.abs(projected[0]) < 1 && Math.abs(projected[1]) < 1);
        }
    }
  assert.deepEqual(triangles, before);
});

test("drawing buffer has a fixed pixel budget and handles high-density/mobile sizes", () => {
  for (const [width, height, ratio] of [
    [360, 220, 3],
    [1280, 420, 2],
    [8000, 5000, 4],
    [0, 0, 1],
  ]) {
    const size = geometry.renderSize(width, height, ratio);
    assert.ok(size.width >= 1 && size.height >= 1);
    assert.ok(size.width * size.height <= 600000);
    assert.ok(size.width <= 1600 && size.height <= 1000);
  }
});

function rendererModule() {
  const source = readFileSync(
    new URL("../app/_components/car-renderer.ts", import.meta.url),
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
    () => geometry,
    module,
    module.exports,
  );
  return module.exports;
}

test("unsupported WebGL returns a safe fallback without allocating a renderer", () => {
  assert.equal(
    rendererModule().createCarRenderer({ getContext: () => null }, () => {}),
    null,
  );
});

function fakeGL(linked = true) {
  const deleted = [];
  let lost = false;
  const gl = new Proxy(
    {
      createShader: () => ({}),
      createProgram: () => ({}),
      createBuffer: () => ({}),
      getProgramParameter: () => linked,
      getAttribLocation: () => 0,
      getUniformLocation: () => ({}),
      isContextLost: () => lost,
      deleteShader: () => deleted.push("shader"),
      deleteProgram: () => deleted.push("program"),
      deleteBuffer: () => deleted.push("buffer"),
      getExtension: () => ({
        loseContext: () => {
          lost = true;
        },
      }),
    },
    { get: (target, key) => target[key] ?? (() => {}) },
  );
  return {
    gl,
    deleted,
    lose: () => {
      lost = true;
    },
  };
}

test("shader failure releases allocated GPU resources and leaves a fallback", () => {
  const { gl, deleted } = fakeGL(false);
  assert.equal(
    rendererModule().createCarRenderer(
      { getContext: () => gl, removeEventListener() {} },
      () => {},
    ),
    null,
  );
  assert.equal(deleted.filter((item) => item === "shader").length, 2);
  assert.ok(deleted.includes("program"));
});

test("scene has no animation loop, releases resources and reports context loss", () => {
  const previous = globalThis.ResizeObserver;
  let disconnected = false;
  globalThis.ResizeObserver = class {
    observe() {}
    disconnect() {
      disconnected = true;
    }
  };
  const { gl, deleted, lose } = fakeGL();
  const events = new Map();
  const canvas = {
    getContext: () => gl,
    clientWidth: 720,
    clientHeight: 320,
    addEventListener: (name, fn) => events.set(name, fn),
    removeEventListener: (name) => events.delete(name),
  };
  let failures = 0;
  try {
    const renderer = rendererModule().createCarRenderer(
      canvas,
      () => failures++,
    );
    assert.ok(renderer);
    assert.equal(renderer.draw(0), true);
    lose();
    events.get("webglcontextlost")({ preventDefault() {} });
    assert.equal(failures, 1);
    assert.equal(renderer.draw(0), false);
    renderer.dispose();
    renderer.dispose();
    assert.ok(disconnected);
    assert.equal(deleted.filter((item) => item === "buffer").length, 1);
    assert.equal(events.size, 0);
  } finally {
    globalThis.ResizeObserver = previous;
  }
});

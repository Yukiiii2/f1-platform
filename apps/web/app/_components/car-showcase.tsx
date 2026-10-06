"use client";

import Image from "next/image";
import { useEffect, useId, useRef, useState } from "react";
import type { CarRenderer } from "./car-renderer";
import "./car-showcase.css";

const INITIAL_ANGLE = -31.5;
export function CarShowcase() {
  const id = useId();
  const canvas = useRef<HTMLCanvasElement>(null);
  const renderer = useRef<CarRenderer | null>(null);
  const sequence = useRef(0);
  const figure = useRef<HTMLElement>(null);
  const restoreFocus = useRef(false);
  const rotationControl = useRef<HTMLInputElement>(null);
  const exploreControl = useRef<HTMLButtonElement>(null);
  const previousStatus = useRef("static");
  const [status, setStatus] = useState<
    "static" | "loading" | "ready" | "unavailable"
  >("static");
  const [angle, setAngle] = useState(INITIAL_ANGLE);
  const [generation, setGeneration] = useState(0);
  useEffect(() => {
    if (previousStatus.current !== status && status !== "loading") {
      if (
        restoreFocus.current &&
        (document.activeElement === document.body ||
          figure.current?.contains(document.activeElement))
      ) {
        if (status === "ready") rotationControl.current?.focus();
        else exploreControl.current?.focus();
      }
      restoreFocus.current = false;
    }
    previousStatus.current = status;
  }, [status]);
  useEffect(
    () => () => {
      sequence.current++;
      renderer.current?.dispose();
      renderer.current = null;
    },
    [],
  );
  function fallback(next: "static" | "unavailable") {
    restoreFocus.current =
      Boolean(figure.current?.contains(document.activeElement)) ||
      (previousStatus.current === "loading" && restoreFocus.current);
    sequence.current++;
    renderer.current?.dispose();
    renderer.current = null;
    setGeneration((value) => value + 1);
    setAngle(INITIAL_ANGLE);
    setStatus(next);
  }
  async function enable() {
    restoreFocus.current = Boolean(
      figure.current?.contains(document.activeElement),
    );
    const token = ++sequence.current;
    setStatus("loading");
    try {
      // The WebGL implementation and geometry are downloaded only on request.
      const { createCarRenderer } = await import("./car-renderer");
      if (token !== sequence.current || !canvas.current) return;
      const scene = createCarRenderer(canvas.current, () => {
        if (token === sequence.current) fallback("unavailable");
      });
      if (!scene) {
        fallback("unavailable");
        return;
      }
      renderer.current = scene;
      setStatus("ready");
    } catch {
      if (token === sequence.current) fallback("unavailable");
    }
  }
  function turn(value: number) {
    setAngle(value);
    try {
      if (!renderer.current?.draw((value * Math.PI) / 180))
        fallback("unavailable");
    } catch {
      fallback("unavailable");
    }
  }
  return (
    <figure
      ref={figure}
      className="car-showcase"
      aria-labelledby={`${id}-title`}
    >
      <figcaption>
        <h2 id={`${id}-title`}>Open-wheel form.</h2>
        <p>
          Illustrative model. Authored geometry, not a team car or race replay.
        </p>
      </figcaption>
      <div className="car-stage" data-ready={status === "ready"}>
        <Image
          className="car-static"
          src="/illustrations/open-wheel-car.svg"
          alt="A stylized open-wheel racing car with exposed wheels, front and rear wings, and an orange accent."
          fill
          sizes="(max-width: 600px) 100vw, 1280px"
          unoptimized
        />
        <canvas key={generation} ref={canvas} aria-hidden="true" />
      </div>
      <div className="car-controls">
        {status === "ready" ? (
          <>
            <div className="car-view">
              <label htmlFor={`${id}-rotation`}>View angle</label>
              <input
                ref={rotationControl}
                id={`${id}-rotation`}
                type="range"
                min={-180}
                max={180}
                step={1}
                value={angle}
                onChange={(event) => turn(Number(event.target.value))}
                aria-describedby={`${id}-help`}
              />
            </div>
            <button
              type="button"
              className="button button-quiet"
              onClick={() => turn(INITIAL_ANGLE)}
            >
              Reset view
            </button>
            <button
              type="button"
              className="button button-quiet"
              onClick={() => fallback("static")}
            >
              Use static view
            </button>
          </>
        ) : (
          <button
            ref={exploreControl}
            type="button"
            className="button button-quiet"
            disabled={status === "loading"}
            onClick={enable}
          >
            {status === "loading"
              ? "Loading 3D…"
              : status === "unavailable"
                ? "Try 3D again"
                : "Explore in 3D"}
          </button>
        )}
        <p id={`${id}-help`} className="car-note">
          {status === "ready"
            ? "Use the slider or arrow keys to rotate. No automatic motion."
            : "The static illustration stays available without 3D."}
        </p>
      </div>
      <p role="status" aria-live="polite" className="car-note">
        {status === "loading"
          ? "Loading the optional 3D view."
          : status === "unavailable"
            ? "3D is unavailable on this device. The static illustration and race data remain available."
            : status === "ready"
              ? "Interactive 3D view ready."
              : ""}
      </p>
    </figure>
  );
}

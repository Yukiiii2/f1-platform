# AGENTS.md — F1 Intelligence Platform

## Core rule

Make the smallest correct change for the user's request.

Do not fix unrelated issues, refactor unrelated code, explore broadly, add dependencies, run full builds/tests, or redesign adjacent features unless required or explicitly requested.

## Read only what the task needs

- UI/design task -> `PRODUCT.md`, `DESIGN.md`, `DESIGN_GUIDELINES.md`
- Backend/API/schema/ingestion task -> `ARCHITECTURE.md`, `DATA_AND_TELEMETRY.md`
- Telemetry/strategy task -> `DATA_AND_TELEMETRY.md`, plus `ARCHITECTURE.md` only if needed
- AI/Pitwall task -> `AI.md`, `DATA_AND_TELEMETRY.md`
- Phase/roadmap task -> `ROADMAP.md`
- Existing feature change -> inspect the current implementation first

Do not load every project document by default.

## Scope

Before editing, determine:
1. requested outcome;
2. directly affected files;
3. minimum context needed.

If the user names a file, edit only that file unless another change is required for correctness. Reading a dependency does not grant permission to modify it.

When no file is named:
`feature -> likely implementation -> direct dependencies`

Avoid repository-wide exploration.

## Existing code

Existing code is the implementation source of truth.

Reuse:
- current structure;
- components;
- utilities;
- schemas;
- services;
- naming;
- API patterns;
- styling conventions.

Do not create a new abstraction when the existing project already has one.

## Commands and validation

Use the fewest commands necessary.

Do not run by default:
- full builds;
- full test suites;
- repository-wide lint/typecheck;
- Playwright/Cypress;
- Docker Compose;
- deployment/CI commands.

Run only narrow validation when requested or necessary for a risky change.

Do not repeatedly inspect information already known.

## Dependencies

Do not add/remove/upgrade dependencies unless required for the requested feature.

Prefer existing packages.

Never commit secrets. Use environment variables and `.env.example`.

## Frontend

Follow the design docs.

The product should feel like premium motorsport editorial + race engineering, not a generic SaaS dashboard.

Avoid:
- excessive cards/pills;
- unnecessary gradients/glows;
- glassmorphism;
- fake technical decoration;
- turning the whole site into WebGL.

3D is optional enhancement. Core data and navigation must work without it.

## Architecture

Frontend consumes application APIs, not third-party F1 APIs directly for core features.

Backend owns:
- provider adapters;
- ingestion;
- normalization;
- validation;
- persistence;
- derived metrics;
- caching.

PostgreSQL is the durable application source of truth.

Ingestion must be idempotent and retry-safe.

Do not leak provider response shapes into core domain APIs.

## F1 data accuracy

Every value is one of:

**Source** — directly supplied by an upstream source.

**Derived** — deterministic calculation from source data.

**Estimate / AI interpretation** — heuristic or model-produced.

Never present an estimate as official telemetry.

Do not invent unavailable data such as:
- tyre temperature;
- tyre pressure;
- brake pressure;
- fuel load;
- aero load;
- engine modes;
- team-only setup data.

Tyre age must use source stint metadata when available.

3D/replay data is reconstructed unless the source explicitly provides authoritative positioning.

## Pitwall AI

For event-specific claims, use application data/tools before model memory.

Pitwall must:
- retrieve relevant data;
- distinguish fact, calculation, and interpretation;
- state when data is unavailable;
- avoid fake causal certainty;
- never invent telemetry channels.

## Destructive actions

Ask before:
- deleting significant code/data;
- destructive migrations;
- force pushes/history rewrites;
- production infrastructure changes;
- secret changes;
- major dependency upgrades.

## Completion

Report only:
- what changed;
- files changed;
- important decision/blocker;
- validation performed, if any.

Then stop.

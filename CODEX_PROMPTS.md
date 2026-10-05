# Token-Efficient Codex Prompt Pack

## Usage rule

Do **not** paste the full project specification into every Codex request.

`AGENTS.md` tells Codex which project docs to read.

For each phase, send only the corresponding prompt below.

---

## 00 — Repository Foundation

Read `AGENTS.md` and the docs it requires for this task.

Implement **Roadmap Phase 0 only**.

Prepare the monorepo foundation for:
- `apps/web`
- `apps/api`
- `packages/shared`
- `packages/ui`
- `infra`
- `scripts`

Keep web and API independently runnable.

Also prepare `.env.example` with placeholders only.

Do not implement F1 data ingestion, telemetry, AI, authentication, or 3D yet.

Preserve useful existing code.

Do not run full builds/tests unless necessary or requested.

At the end, report changed files and the local commands I should run.
---

## 01 — Backend Domain

Read `AGENTS.md`.

Implement **Roadmap Phase 1 only**.

Create the FastAPI/PostgreSQL foundation:
- config;
- DB session;
- SQLAlchemy;
- Alembic;
- `/v1`;
- health route;
- Season;
- Event;
- Circuit;
- Session;
- Driver;
- Team;
- Result;
- DriverStanding;
- ConstructorStanding;
- Pydantic schemas.

Keep provider IDs separate from domain IDs.

No telemetry, AI, auth, or provider integration yet.

Use timezone-aware timestamps where applicable.

Do not run broad validation.
---

## 02 — Provider + Core Ingestion

Read `AGENTS.md`.

Implement **Roadmap Phase 2 only**.

Add:
- provider abstraction;
- one initial F1 provider;
- normalization;
- idempotent ingestion;
- import metadata;
- events/circuits/drivers/teams/sessions/results/standings;
- stable read APIs.

Provider models must not become core domain models.

No telemetry, AI, live timing, or frontend redesign.

At completion, summarize persisted upstream fields and intentionally ignored fields.
---

## 03 — Core Frontend

Read `AGENTS.md`.

Implement **Roadmap Phase 3 only** using the existing backend.

Pages:
- Home
- Races
- Race detail
- Drivers
- Driver detail
- Standings

Requirements:
- responsive;
- accessible;
- premium motorsport/data design;
- proper loading/error/empty states;
- no fake production stats.

No telemetry, AI, or 3D yet.

Do not redesign unrelated areas.
---

## 04 — Telemetry Storage + Ingestion

Read `AGENTS.md`.

Implement **Roadmap Phase 4 only**.

Add normalized storage and ingestion for supported provider data:
- Lap
- TelemetrySample
- Stint
- PitStop
- PositionSample
- IntervalSample
- RaceControlMessage
- WeatherSample

Keep raw source values intact and imports idempotent.

Preserve tyre age at stint start when supplied.

Expose read APIs for laps, telemetry, stints, pits, race control, positions, and intervals.

Do not invent unsupported telemetry.

No AI or Telemetry Lab UI yet.
---

## 05 — Telemetry Comparison Engine

Read `AGENTS.md`.

Implement the backend lap-comparison service only.

Support:
- two laps;
- lap/sector deltas;
- synchronized traces;
- tyre context;
- deterministic tyre-age calculation.

Define in code/docs:
- alignment method;
- interpolation method;
- delta sign convention;
- missing-sample behavior.

Keep raw data unchanged.

Expose `POST /v1/telemetry/compare` or the existing equivalent.

No AI/UI changes.
---

## 06 — Telemetry Lab

Read `AGENTS.md`.

Build the Telemetry Lab using existing APIs.

Flow:
event -> session -> Driver A/lap -> Driver B/lap -> compare.

Show:
- lap/sector times;
- tyre compound/age;
- speed;
- throttle;
- brake state;
- gear;
- RPM;
- DRS;
- delta.

Prioritize chart readability, responsive behavior, and accessibility.

No fake tyre temperature, brake pressure, or tyre-health percentage.

No 3D replay yet.
---

## 07 — Strategy + Tyres

Read `AGENTS.md`.

Build the completed-race strategy view.

Show:
- compounds;
- stint boundaries;
- tyre age at stint start;
- stint usage;
- derived total tyre age;
- pit stops;
- valid pace metrics;
- safety-car/VSC context when available.

Support driver comparison.

Clearly separate source, derived, and estimated values.

Do not infer team intent as fact.
---

## 08 — Pitwall AI Backend

Read `AGENTS.md`.

Implement the Pitwall backend only.

Add:
- AI service boundary;
- `/v1/ai/query`;
- structured page context;
- tools for drivers, events/sessions, results, laps, telemetry, stints, pits, standings, race control, weather, and lap comparison.

Event-specific answers must use application services/data before model memory.

Never expose keys or invent unavailable telemetry.

No frontend AI UI yet.
---

## 09 — Pitwall Frontend

Read `AGENTS.md`.

Integrate Pitwall into:
- race pages;
- driver pages;
- Telemetry Lab;
- strategy view.

Pass structured current context.

Show retrieval/analysis state.

Keep sourced facts, calculations, and interpretation visually distinguishable when the API provides that distinction.

Do not turn it into a generic detached chat widget.

Avoid backend changes unless required for integration correctness.
---

## 10 — First 3D Feature

Read `AGENTS.md`.

Implement **one** polished 3D experience only.

Prefer the current best fit between:
- homepage hero;
- circuit/telemetry visualization.

Requirements:
- lazy loading;
- static/non-WebGL fallback;
- reduced-motion support;
- mobile-conscious performance;
- no loss of core data if 3D fails.

Do not redesign the entire site or make the whole app WebGL.
---

## 11 — Automatic Post-Session Updates

Read `AGENTS.md`.

Implement **Roadmap Phase 9 only**.

After a session is confirmed complete:
1. detect it;
2. run idempotent final ingestion;
3. import supported result/lap/telemetry/stint/pit/race-control data;
4. validate;
5. calculate derived values;
6. update standings where appropriate;
7. invalidate affected caches;
8. optionally enqueue the AI report.

Jobs must be retry-safe and observable.

Do not use excessive polling.

Do not call it real-time unless the configured provider actually supplies real-time data.
---

## 12 — V1 Production Review

Read `AGENTS.md`.

Review V1 only. Do not refactor yet.

Find:
- data correctness issues;
- ingestion/idempotency problems;
- schema/index issues;
- telemetry calculation risks;
- cache issues;
- AI grounding risks;
- exposed secrets;
- frontend performance issues;
- 3D loading problems;
- accessibility issues;
- deployment blockers.

Return findings as:
`severity | file | issue | smallest fix`

Severity:
- Blocker
- High
- Medium
- Low

Do not implement fixes until requested.

# Roadmap

## Phase 0 — Repository Foundation

Goals:
- monorepo structure;
- project docs;
- environment templates;
- formatting/lint baseline;
- basic web/API bootstrapping.

Deliverables:
- `apps/web`;
- `apps/api`;
- shared configuration;
- `.env.example`;
- README;
- docs.

Do not build advanced UI yet.

---

## Phase 1 — Core Backend Domain

Goals:
- FastAPI structure;
- PostgreSQL connection;
- SQLAlchemy models;
- Alembic;
- core domain entities.

Initial entities:
- Season
- Event
- Circuit
- Session
- Driver
- Team
- Result
- DriverStanding
- ConstructorStanding

---

## Phase 2 — Data Provider Integration

Goals:
- provider adapter abstraction;
- first provider client;
- schedule/events;
- drivers/teams;
- results;
- standings;
- idempotent ingestion.

Deliver:
- ingestion jobs;
- import metadata;
- retries;
- normalization.

---

## Phase 3 — Core Frontend

Goals:
- application shell;
- homepage;
- races;
- driver pages;
- standings;
- responsive foundation.

Use real backend contracts, not hardcoded production data.

---

## Phase 4 — Telemetry Data Pipeline

Goals:
- laps;
- telemetry samples;
- stints;
- pit stops;
- race control;
- position/interval samples;
- tyre-age calculations.

Deliver:
- normalized storage;
- raw/derived separation;
- telemetry APIs.

---

## Phase 5 — Telemetry Lab

Goals:
- event/session/lap selectors;
- lap comparison;
- speed/throttle/brake/gear/RPM/DRS traces;
- sector comparison;
- delta trace;
- tyre context.

---

## Phase 6 — Strategy and Tyres

Goals:
- stint timeline;
- compound display;
- tyre age;
- pit-stop overlay;
- average pace;
- strategy comparison.

---

## Phase 7 — Pitwall AI

Goals:
- AI endpoint;
- tool calling;
- contextual route data;
- driver/race/session/lap tools;
- grounded answers;
- source/derived/interpretation distinction.

---

## Phase 8 — 3D Experience

Goals:
- one polished 3D hero;
- circuit visualization;
- optional lap replay.

Requirements:
- lazy loaded;
- fallback;
- responsive;
- reduced-motion aware.

---

## Phase 9 — Automatic Race Weekend Updating

Goals:
- session-aware scheduler;
- post-session sync;
- finalization job;
- cache invalidation;
- AI race report generation.

---

## Phase 10 — Production Hardening

Goals:
- narrow test coverage around critical calculations;
- monitoring;
- ingestion reliability;
- performance;
- deployment;
- error handling;
- documentation.

---

## Later / V2

Potential:
- near-live session updates;
- multi-car race replay;
- user accounts;
- saved comparisons;
- predictions;
- historical seasons;
- advanced tyre-degradation models;
- personalized dashboards.

Do not pull V2 work into V1 unless explicitly requested.

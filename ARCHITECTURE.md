# Architecture

## Overview

Use a monorepo:

```text
f1-platform/
├── apps/
│   ├── web/
│   └── api/
├── packages/
│   ├── shared/
│   └── ui/
├── infra/
├── scripts/
├── docs/
├── AGENTS.md
├── PRODUCT.md
├── DESIGN.md
├── DESIGN_GUIDELINES.md
├── ARCHITECTURE.md
├── DATA_AND_TELEMETRY.md
├── AI.md
├── ROADMAP.md
└── README.md
```

---

## Initial Stack

### Web
- Next.js
- React
- TypeScript
- Tailwind CSS
- React Three Fiber / Drei
- Motion and/or GSAP where justified

### API
- FastAPI
- Python
- SQLAlchemy
- Alembic
- Pydantic

### Data
- PostgreSQL
- Redis

### Jobs
Start with a simple scheduler/background worker abstraction.
Use Celery, ARQ, Dramatiq, or another worker only when the actual workload justifies it.

Do not introduce operational complexity prematurely.

---

## System Flow

```text
External F1 sources
        |
        v
Ingestion adapters
        |
        v
Normalization
        |
        v
Validation
        |
        v
PostgreSQL
   |         |
   v         v
Derived     Cache
metrics     Redis
   \         /
    \       /
      API
       |
       v
   Next.js
       |
       +------> Pitwall AI
```

---

## Source Ownership

Third-party providers are upstream sources.

The backend owns:
- ingestion;
- provider adapters;
- normalization;
- validation;
- deduplication;
- persistence;
- derived metrics;
- caching;
- API contracts.

The frontend should consume application APIs, not provider APIs directly for core features.

---

## Core Domain

Suggested domain entities:
- Season
- Event
- Circuit
- Session
- Driver
- Team
- Entry
- Result
- Lap
- TelemetrySample
- Stint
- PitStop
- PositionSample
- IntervalSample
- RaceControlMessage
- WeatherSample
- DriverStanding
- ConstructorStanding
- AIReport

Do not blindly mirror an upstream provider's schema.

---

## API Layers

Suggested structure:

```text
apps/api/app/
├── api/
├── core/
├── db/
├── domain/
├── models/
├── schemas/
├── services/
├── providers/
├── ingestion/
├── telemetry/
├── ai/
└── workers/
```

Responsibilities:

### providers/
Provider-specific clients and response mapping.

### ingestion/
Idempotent import orchestration.

### domain/
Core application concepts independent of provider.

### services/
Business operations and queries.

### telemetry/
Alignment, interpolation, lap comparison, derived metrics.

### ai/
Tool definitions, retrieval, report generation, analysis orchestration.

---

## Ingestion

Ingestion must be:
- idempotent;
- retryable;
- observable;
- incremental where possible.

Each import should track:
- provider;
- external identifier;
- session;
- import timestamp;
- source update timestamp when available;
- status;
- failure details.

Do not duplicate rows when a job retries.

---

## Race Weekend Updating

### Before session
- sync schedule/session metadata;
- low-frequency polling.

### During active session
V1 does not require real-time support.
If near-live is later enabled, use provider-appropriate polling/streaming and rate limits.

### After session
- detect completion;
- run final result import;
- import laps/telemetry/stints/pits/race control;
- validate;
- compute derived metrics;
- update standings if appropriate;
- invalidate relevant caches;
- optionally generate AI report.

---

## Caching

Use caching for:
- standings;
- event summaries;
- popular driver pages;
- computed lap comparisons;
- expensive telemetry transformations.

Never use Redis as the only durable copy of race data.

---

## Frontend Structure

Suggested:

```text
apps/web/
├── app/
│   ├── races/
│   ├── drivers/
│   ├── teams/
│   ├── circuits/
│   ├── standings/
│   ├── telemetry/
│   └── ai/
├── components/
│   ├── ui/
│   ├── f1/
│   ├── telemetry/
│   ├── strategy/
│   └── three/
├── lib/
│   ├── api/
│   ├── telemetry/
│   └── utils/
└── types/
```

---

## API Contract Philosophy

Prefer stable application-facing endpoints such as:

```text
GET /v1/events
GET /v1/events/{event_id}
GET /v1/sessions/{session_id}
GET /v1/sessions/{session_id}/results
GET /v1/sessions/{session_id}/laps
GET /v1/laps/{lap_id}/telemetry
GET /v1/sessions/{session_id}/stints
GET /v1/standings/drivers
POST /v1/telemetry/compare
POST /v1/ai/query
```

Do not expose provider-specific query conventions through the public application API.

---

## Observability

At minimum, record:
- ingestion successes/failures;
- provider response failures;
- job duration;
- imported row counts;
- AI tool failures;
- unsupported-data requests.

Avoid logging secrets or raw private user content.

---

## Deployment

Likely initial topology:
- Next.js web: Vercel or equivalent;
- FastAPI: Railway/Fly/Render or equivalent;
- PostgreSQL: Neon/Supabase/managed Postgres;
- Redis: managed Redis if/when needed.

Deployment provider is not a product requirement and may change.

# F1 Intelligence Platform

V2 Phase 2 adds historical season browsing through the existing pages. Import a
year explicitly with `python -m app.ingestion --season <YEAR>` using the API virtual
environment and `PYTHONPATH=apps/api`; apply migration `0008_historical_core_sources`
first. Season selectors show recorded core coverage and retain the selected year
in navigation. Core imports do not imply telemetry availability. See the
[historical-season setup and verification commands](apps/api/README.md#historical-seasons-v2-phase-2).

An unofficial Formula 1 data, telemetry, strategy, 3D, and AI analysis platform.

## Status

V1 Phase 0-12 foundation with V2 near-live session updates and historical seasons.
Web and API run independently.
V2 Phase 4 adds local Saved Comparisons at `/comparisons`. Save an existing
Telemetry Lab lap pair or Strategy driver pair and reopen the same selections;
analysis is recalculated from current recorded data. Apply migration
`0009_saved_comparisons` before using it. See
[saved-comparison storage, ownership and API notes](apps/api/README.md#saved-comparisons-v2-phase-4).
Jolpica core data can be imported into PostgreSQL through an explicit local job.
The web provides Home, Races, Race detail, Drivers, Driver detail, Standings,
the Telemetry Lab at `/telemetry`, completed-race Strategy + Tyres at `/strategy`,
and grounded Pitwall analysis at `/pitwall` and within relevant data pages.
All race data comes from the application's persisted domain APIs.
Historical OpenF1 session data can be imported explicitly into normalized storage.
Telemetry read APIs, deterministic tyre-age calculations, and backend lap
comparison are available. The Telemetry Lab compares recorded laps, sectors,
tyre context, and synchronized channels through the existing application APIs.
Strategy compares source stints and pit stops, calculated tyre-age snapshots and
observed non-pit pace, with recorded safety-car/VSC messages. Source boundary
overlaps and missing records remain explicit; no strategy intent is inferred.
The optional Pitwall interface uses `POST /v1/ai/query` with structured page context,
read-only application tools, and evidence-separated facts/calculations/estimates/
interpretations. Configure it server-side as described in `apps/api/README.md`.
Questions and retry controls remain available during temporary service failures.
The Home page includes an optional, on-demand 3D car with a static fallback.
Explicitly registered sessions can be finalized by the separate post-session worker.

V2 Phase 3 adds `/races/[eventId]/replay`, linked from race/sprint detail, and
`GET /v1/sessions/{session_id}/replay?max_samples=300` (32–600 samples per driver).
This is a multi-driver **timing/order replay**, not a circuit or GPS reconstruction:
the stored position records contain race rank only. Replay needs overlapping
usable samples for at least two drivers from one source. Core results alone never
enable replay. Gaps, missing drivers, provisional data and truncated context are
labelled partial; recorded coverage may be shorter than the full session.
Payloads contain at most 32 drivers, 600 position/interval points per driver,
200 laps and 50 pits per driver, and 200 race-control messages. Sampling retains
original timestamps/values, including endpoints; intermediate changes may be
omitted. Playback holds the previous recorded rank for at most 30 seconds and
labels that hold calculated, then marks it unavailable. Lap/pit windows use
recorded starts and durations, with approximate lap starts labelled estimates.
No coordinates, incidents or retirement times are inferred. Playback starts
paused and fetches one snapshot, with no request per frame. Provisional snapshots
can be refreshed using the existing session update control; worker finalization
remains authoritative. No migration or new configuration is required.

## Planned V1

- race weekends;
- driver pages;
- standings;
- automatic post-session data updates;
- qualifying telemetry;
- race-lap telemetry;
- tyre stints and tyre age;
- lap comparison;
- strategy visualization;
- Pitwall AI;
- one polished 3D experience.

## Architecture

See:

- `PRODUCT.md`
- `ARCHITECTURE.md`
- `DATA_AND_TELEMETRY.md`
- `AI.md`
- `ROADMAP.md`

## Repository

```text
apps/
  web/
  api/
packages/
  shared/
  ui/
infra/
scripts/
docs/
```

## Local Development

Prerequisites: Node.js 22+ with npm 10+, and Python 3.11+.
Run these commands from the repository root. Python commands below use PowerShell.

### Web

```powershell
npm install
Copy-Item .env.example apps/web/.env.local
npm run dev:web
```

Open http://localhost:3000. The application shell runs independently; data pages
need the API, a migrated PostgreSQL database, and imported core records.
`NEXT_PUBLIC_API_URL` is the application API base address (without `/v1`), defaulting
to `http://localhost:8000`. Next.js fetches this API on the server, so the address
must be reachable from the web server; browser CORS configuration is not needed.
Remove the unused database/cache placeholders from `apps/web/.env.local`; never
prefix secrets with `NEXT_PUBLIC_`. Do not overwrite an existing environment file.

The frontend supports imported season selection, driver search, session selection,
and driver/constructor standings. A driver profile shows championship data and
results for a selected weekend; constructor identity comes from each session result.
Schedules display UTC, date-only schedules do not invent times, and statuses come
from recorded session data. Unimported data has explicit empty states; connection
failures have a retry action. No demonstration race statistics are shipped.

See [frontend notes](apps/web/README.md) for routes and focused validation.

### API (separate terminal)

```powershell
python -m venv apps/api/.venv
apps/api/.venv/Scripts/python.exe -m pip install -e "apps/api[dev]"
apps/api/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir apps/api --reload --port 8000
```

Open http://localhost:8000 for the bootstrap response,
http://localhost:8000/v1/health for process liveness, or
http://localhost:8000/docs for OpenAPI documentation. Liveness does not check
database readiness; it requires no environment file, database, cache, or web process.

For database operations, provision an empty PostgreSQL database and configure
`DATABASE_URL` in `apps/api/.env` (or your shell environment). Copy the template,
replace its database placeholders, then apply the migrations:

```powershell
Copy-Item .env.example apps/api/.env
# Edit apps/api/.env with your PostgreSQL connection details before continuing.
apps/api/.venv/Scripts/python.exe -m alembic -c apps/api/alembic.ini upgrade head
```

Do not overwrite an existing local environment file. The API loads its `.env`
from `apps/api` regardless of the current working directory. Migrations run
explicitly; application startup never creates tables or applies migrations.
See [backend notes](apps/api/README.md) for the domain contracts and focused checks.

### Core data import

After installing the updated API dependencies and applying migrations, run a
season import (or use `--round 1` to limit it to one event):

```powershell
apps/api/.venv/Scripts/python.exe -m app.ingestion --season 2025
```

This job calls Jolpica, validates and normalizes its core data, and commits it
atomically. Repeated imports preserve domain IDs and update existing records.
Import attempts and failures are recorded in `import_runs`. Manual imports remain
available alongside automatic updates for explicitly registered sessions.
See [ingestion details](apps/api/README.md#core-data-imports)
for source fields, retries, limitations, and the read API routes.

On macOS/Linux, replace `apps/api/.venv/Scripts/python.exe` with
`apps/api/.venv/bin/python` and use `cp` instead of `Copy-Item`.

### Historical session data import

Apply the new migration, then import a historical OpenF1 session into an existing
application session. Map each selected session car number explicitly to an
existing application driver UUID:

```powershell
apps/api/.venv/Scripts/python.exe -m alembic -c apps/api/alembic.ini upgrade head
apps/api/.venv/Scripts/python.exe -m app.ingestion.telemetry --session <application-session-uuid> --source-session <openf1-session-key> --driver "<car-number>=<application-driver-uuid>"
```

Repeat `--driver` for additional drivers. See
[session import instructions](apps/api/README.md#telemetry-data-imports-phase-4)
for finding identifiers, read routes, source coverage, and lap-association limits.
See [lap comparison](apps/api/README.md#lap-comparison-phase-5) for
`POST /v1/telemetry/compare`, alignment rules, and approximate-data opt-in.

Telemetry import ordering is stored separately from immutable raw revisions.
An older overlapping fetch cannot replace a newer normalized observation;
repeated and corrected source payloads retain their raw revision history.

### Automatic post-session updates

Apply migrations and explicitly register each existing application session with
its OpenF1 session key and driver UUID mappings before starting the worker. See
[registration and scheduling](apps/api/README.md#automatic-post-session-updates-phase-11-prompt)
for the supported `--register`, `--status`, `--once`, and `--retry` commands.

```powershell
$env:PYTHONPATH = "apps/api"
apps/api/.venv/Scripts/python.exe -m app.workers --watch
```

The separate worker checks registered sessions every 30 minutes by default and
requires historical settling and completion evidence before finalization. It
refreshes available core data, imports telemetry, and records job status with
bounded retries; PostgreSQL prevents overlapping workers. Stop with Ctrl+C.
Historical-only registration remains the default. V2 Phase 1 optionally enables
near-live refresh with `--register --live`, authenticated OpenF1 access, and bounded
60?300 second polling. Live observations remain provisional until the full
post-session finalization succeeds. Race, Telemetry and Strategy pages label the
state and offer manual refresh; Pitwall preserves provisional evidence labels.
See [near-live setup and limitations](apps/api/README.md#near-live-session-updates-v2-phase-1).
Session discovery and driver mapping remain explicit.

### Pitwall admission protection

Apply migrations through `0006_telemetry_observation_order` before running the
updated API. Stop importers/workers during migration and fetch again afterward;
existing telemetry receives a migration-time ordering watermark. Pitwall defaults
to an aggregate 10 admitted queries/minute,
100/day (UTC), and two concurrent queries, shared across API processes through
PostgreSQL. Optional server-side `PITWALL_REQUESTS_PER_MINUTE`,
`PITWALL_REQUESTS_PER_DAY`, and `PITWALL_MAX_CONCURRENT` override these limits;
use identical values on all API replicas and direct PostgreSQL connections
(session advisory locks require connection affinity, not transaction pooling).
Rejected requests return a safe 429 with `Retry-After`; unavailable protection
fails closed with 503. Admitted failures still consume the request budget.
Existing provider retries and grounded-answer behavior remain unchanged.

### Formatting and lint baseline

Run only the checks relevant to your changes:

```powershell
npm run lint:web
npm run format:check
apps/api/.venv/Scripts/python.exe -m ruff check apps/api/app
apps/api/.venv/Scripts/python.exe -m ruff format --check apps/api/app
```

`npm run format` formats supported files; the supplied project specifications
are excluded. Python formatting uses Ruff. Shared TypeScript settings live in
`tsconfig.base.json`; editor whitespace settings live in `.editorconfig`.

The workspace packages `@f1/shared` and `@f1/ui` are reserved directories with
no runtime exports yet. `infra`, `scripts`, and `docs` contain scope/setup notes.
The backend includes the nine core domain models, Pydantic schemas, Alembic,
provider identity mappings, import metadata, core ingestion, and read APIs.
The core frontend consumes the core read APIs. The backend also stores supported
lap, telemetry, stint, pit, position, interval, race-control, and weather data.
Backend lap comparison, Telemetry Lab, Strategy + Tyres, and grounded Pitwall all
read this persisted data. Automatic updates require explicit registration; the
optional 3D car is authored artwork, not a telemetry replay. Authentication and
live timing remain outside the implemented scope.

## Disclaimer

This is an unofficial fan/data project and is not affiliated with Formula 1, the FIA, Formula One Management, any Formula 1 team, or any driver.

Third-party data and media remain subject to their respective licenses and terms.

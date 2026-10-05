# F1 Intelligence Platform

An unofficial Formula 1 data, telemetry, strategy, 3D, and AI analysis platform.

## Status

Phase 4 — telemetry storage and ingestion, alongside the Phase 3 core frontend.
Web and API run independently.
Jolpica core data can be imported into PostgreSQL through an explicit local job.
The web provides Home, Races, Race detail, Drivers, Driver detail, and Standings.
All race data comes from the application's persisted domain APIs.
Historical OpenF1 session data can be imported explicitly into normalized storage.
Telemetry read APIs and deterministic tyre-age calculations are available; the
Telemetry Lab UI remains planned.

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
Import attempts and failures are recorded in `import_runs`. Imports are explicit;
no scheduler or live timing is implemented. See [ingestion details](apps/api/README.md#core-data-imports)
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
Telemetry comparison and UI, AI, authentication, live timing, and 3D remain planned.

## Disclaimer

This is an unofficial fan/data project and is not affiliated with Formula 1, the FIA, Formula One Management, any Formula 1 team, or any driver.

Third-party data and media remain subject to their respective licenses and terms.

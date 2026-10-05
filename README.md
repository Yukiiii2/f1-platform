# F1 Intelligence Platform

An unofficial Formula 1 data, telemetry, strategy, 3D, and AI analysis platform.

## Status

Phase 1 — backend domain foundation. Web and API run independently.
PostgreSQL models, validation schemas, and an initial migration are available.
Provider integration and race-data ingestion are not implemented yet.

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

Open http://localhost:3000. The web runs without the API or a database.
`NEXT_PUBLIC_API_URL` reserves the application API address for future integration;
the Phase 0 page does not fetch data. Remove the unused database/cache placeholders
from `apps/web/.env.local`; never prefix secrets with `NEXT_PUBLIC_`.

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
replace its database placeholders, then apply the initial migration:

```powershell
Copy-Item .env.example apps/api/.env
# Edit apps/api/.env with your PostgreSQL connection details before continuing.
apps/api/.venv/Scripts/python.exe -m alembic -c apps/api/alembic.ini upgrade head
```

Do not overwrite an existing local environment file. The API loads its `.env`
from `apps/api` regardless of the current working directory. Migrations run
explicitly; application startup never creates tables or applies migrations.
See [backend notes](apps/api/README.md) for the domain contracts and focused checks.

On macOS/Linux, replace `apps/api/.venv/Scripts/python.exe` with
`apps/api/.venv/bin/python` and use `cp` instead of `Copy-Item`.

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
The backend now includes configuration, database sessions, nine domain models,
Pydantic create/read schemas, and Alembic. There is no provider integration,
ingestion, telemetry, AI, authentication, or 3D implementation.

## Disclaimer

This is an unofficial fan/data project and is not affiliated with Formula 1, the FIA, Formula One Management, any Formula 1 team, or any driver.

Third-party data and media remain subject to their respective licenses and terms.

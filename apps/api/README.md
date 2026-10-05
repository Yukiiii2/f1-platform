# Backend foundation and core ingestion

Phase 1 adds configuration, PostgreSQL sessions, nine core models, Pydantic
create/read schemas, `/v1/health`, and the initial Alembic revision. Setup and
startup commands are in the [root README](../../README.md).
Phase 2 adds the Jolpica adapter, explicit core imports, provider identity mappings,
import metadata, read APIs, date-only schedule fields, and nullable standings ranks.

## Configuration and database lifecycle

`app.core.config.Settings` reads `DATABASE_URL` from the environment or
`apps/api/.env`. Environment variables take precedence. Only PostgreSQL URLs
using `postgres`, `postgresql`, or `postgresql+psycopg` are supported; connections
use psycopg 3. The URL is excluded from settings representations.

The engine and session factory are lazy. `app.db.session.get_db` yields a session
and closes it after the request. Services must commit explicitly; uncommitted
work is rolled back when the session closes. The API performs no database work
at import time. `GET /v1/health` reports process liveness, not database readiness.

Run migrations against your configured local database from the repository root:

```powershell
apps/api/.venv/Scripts/python.exe -m alembic -c apps/api/alembic.ini upgrade head
```

With a valid `DATABASE_URL`, SQL can also be reviewed without opening a connection:

```powershell
apps/api/.venv/Scripts/python.exe -m alembic -c apps/api/alembic.ini upgrade head --sql
```

The revision has a reverse migration, which removes the domain tables and data.
Do not downgrade a populated database without reviewing the data loss.
Returning from Phase 2 to Phase 1 also requires resolving null standings ranks,
because the earlier schema required numeric positions.

## Domain contracts

Models live in `app.models`; create/read schemas live in `app.schemas`.

| Entity              | Identity and associations                                                |
| ------------------- | ------------------------------------------------------------------------ |
| Season              | Unique championship year, starting at 1950                               |
| Circuit             | Name, country, optional locality and IANA timezone                       |
| Event               | Season, circuit, unique round within a season, optional schedule         |
| Session             | Event, unique session type within an event, status and optional schedule |
| Driver              | Names, optional three-letter code, permanent number and nationality      |
| Team                | Name and optional nationality                                            |
| Result              | Session, driver and team; one result per session/driver                  |
| DriverStanding      | Driver championship snapshot after an event                              |
| ConstructorStanding | Team championship snapshot after an event                                |

All entities have application-generated UUID primary keys. Upstream IDs must
never replace these UUIDs or domain foreign keys. Phase 2 stores provider
identifiers separately in `provider_identities`, keyed by provider and entity kind.
These internal mappings never appear in public core API responses.
Driver/team names and driver numbers are not unique identifiers, and team
membership is recorded on results rather than fixed permanently on a driver.

Schedules and audit timestamps use PostgreSQL `TIMESTAMP WITH TIME ZONE`.
Schemas require timezone-aware datetime values and reject reversed time windows.
Audit timestamps are database-generated; SQLAlchemy updates `updated_at` on
application updates. `scheduled_date` retains source dates even when an exact
time is unavailable; no midnight timestamp is synthesized. Event schedules refer
to the race's scheduled date/start, not the duration of the entire weekend.
Missing schedules are nullable. Session status defaults to
`unknown` and is never inferred from the clock.

Result positions, points, lap counts, times and gaps are nullable when unavailable.
Durations and gaps use integer milliseconds. Points use decimal values with
three fractional digits; no float calculations are introduced. Grid position 0
denotes a pit-lane start; null denotes unavailable grid information.

Standings store explicit points, wins and positions after the referenced event,
not calculated values or season-only overwrites. Positions remain null for
source entries with no numeric championship rank. Each snapshot is unique per
event/driver or event/team. A composite foreign key ensures that the event
belongs to the supplied season. Create schemas reject unknown fields and do not
accept application IDs or audit timestamps.

## Core data imports

The initial provider is [Jolpica](https://github.com/jolpica/jolpica-f1/blob/main/docs/README.md).
`F1Provider` defines the adapter boundary. Raw provider envelopes stay in
`app.providers`; the ingestion service receives provider-independent records
and validates resolved domain fields against the existing Pydantic schemas.

After installing `apps/api[dev]` and migrating to head, run from the repository root:

```powershell
apps/api/.venv/Scripts/python.exe -m app.ingestion --season 2025
# Optional: import just one event and its standings snapshot.
apps/api/.venv/Scripts/python.exe -m app.ingestion --season 2025 --round 1
```

The job fetches the full schedule, driver/team catalogs, race/qualifying/sprint
classifications, and driver/constructor standings for the requested scope.
Without `--round`, the standings endpoint supplies its latest available snapshot;
the returned season and round determine the event association. Historical
snapshots can be imported explicitly with `--round`. They are never relabelled
as the last scheduled or latest completed race.

HTTP requests use a custom user agent, timeout, pacing, complete pagination, and
at most three attempts for transport errors, HTTP 429, and server errors.
Retries honor `Retry-After`; waits above 60 seconds fail the job for a later retry.
Other HTTP failures and malformed/inconsistent pages fail immediately. There
is no polling, scheduler, or public write endpoint.

Import metadata is committed before upstream IO. All domain writes and the
success status commit in one transaction. Failures roll back domain changes and
are recorded separately with sanitized failure details. PostgreSQL transaction
advisory locks serialize writes per provider, including shared identities across
seasons. Serialization/deadlock/unique conflicts retry the data transaction at
most three times. Each rerun creates a new import audit record but reuses existing
domain UUIDs and natural-key records. Sparse driver identity fields do not erase
known values; unavailable schedule times and result timing values clear old data.
No records are deleted merely because an upstream response omits them.

`import_runs` stores provider, requested season/round identifier, linked season,
start/finish/fetch timestamps, status, data-transaction attempt count, normalized
row counts, and failure details. These jobs span multiple sessions, so their
optional session link stays null. Source update timestamps remain null because
this adapter has no authoritative source-update field. Provider mappings are
polymorphic identity records; ingestion checks their target exists. Future
provider adapters must explicitly reconcile identities rather than match names.

### Persisted source fields

- Season year, event round/name, circuit name/country/locality, race date/time,
  and available practice/qualifying/sprint/sprint-qualifying dates/times.
- Driver names, code, permanent number and nationality; team name/nationality.
- Race/sprint driver/team associations, position, grid, points, completed laps,
  finishing status, and `Time.millis` as total elapsed milliseconds.
- Qualifying classification position and driver/team associations. Q1/Q2/Q3
  durations are not total session elapsed times and are not stored in `Result`.
- Driver/constructor standings position, decimal points and wins, linked to the
  source snapshot's event and season. Provider identity values live separately.

**Calculated:** textual `+time` gaps are converted to integer milliseconds using
decimal arithmetic. Lap-count gaps are not turned into time gaps. A session is
marked `completed` when a published classification is available. New sessions
without classifications stay unknown; omitted results do not downgrade an
already completed session. No live/upcoming state is inferred from the clock.

**Intentionally ignored:** provider response wrappers/URLs, Wikipedia links,
driver birth dates, coordinates, per-event car numbers, position display text,
fastest-lap ranks/times/speeds, Q1/Q2/Q3 durations, and historical driver-team
membership lists. No practice classifications, sprint-qualifying classifications,
telemetry, tyre data, or unsupported engineering channels are invented.
Sources missing required domain associations fail validation atomically rather
than receiving fabricated fallback values. Missing standings ranks are stored
as null and sort after ranked entries.

## Read APIs

All routes query PostgreSQL; none call the provider during a request. Lists
return arrays with deterministic ordering and `limit` (1–200, default 50) and
`offset` (nonnegative). Missing detail/parent resources return 404, valid empty
collections return `[]`, and unavailable/unconfigured databases return 503.
The existing `/v1/health` remains process liveness and does not query the database.

- `GET /v1/seasons`
- `GET /v1/events?season=2025` (season filter optional)
- `GET /v1/events/{event_id}` and `/v1/events/{event_id}/sessions`
- `GET /v1/sessions/{session_id}` and `/v1/sessions/{session_id}/results`
- `GET /v1/circuits` and `/v1/circuits/{circuit_id}`
- `GET /v1/drivers` and `/v1/drivers/{driver_id}`
- `GET /v1/teams` and `/v1/teams/{team_id}`
- `GET /v1/standings/drivers?season=2025`
- `GET /v1/standings/constructors?season=2025`

Standings may take an optional `event_id` for a specific stored snapshot. Without
it, each category selects the highest imported event round with stored standings,
not the highest scheduled round. All resource IDs in public responses are domain UUIDs.

## Focused validation

These checks cover configuration, liveness, datetime validation, missing values,
domain integrity, migration reversal, and PostgreSQL SQL generation:

```powershell
apps/api/.venv/Scripts/python.exe -m unittest discover -s apps/api/tests -p test_phase1.py -v
apps/api/.venv/Scripts/python.exe -m unittest discover -s apps/api/tests -p test_phase2.py -v
apps/api/.venv/Scripts/python.exe -m ruff check apps/api/app apps/api/migrations apps/api/tests
apps/api/.venv/Scripts/python.exe -m ruff format --check apps/api/app apps/api/migrations apps/api/tests
```

The persistence tests run migrations on temporary in-memory SQLite and compile
PostgreSQL SQL. They do not establish a live PostgreSQL connection or substitute
SQLite for the application's configured PostgreSQL database.

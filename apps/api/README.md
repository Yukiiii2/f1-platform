# Backend domain foundation

Phase 1 adds configuration, PostgreSQL sessions, nine core models, Pydantic
create/read schemas, `/v1/health`, and the initial Alembic revision. Setup and
startup commands are in the [root README](../../README.md).

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
never replace these UUIDs or domain foreign keys. Provider ID mappings and
provider-specific fields are deferred to Phase 2; no provider integration exists.
Driver/team names and driver numbers are not unique identifiers, and team
membership is recorded on results rather than fixed permanently on a driver.

Schedules and audit timestamps use PostgreSQL `TIMESTAMP WITH TIME ZONE`.
Schemas require timezone-aware datetime values and reject reversed time windows.
Audit timestamps are database-generated; SQLAlchemy updates `updated_at` on
application updates. Missing schedules are nullable. Session status defaults to
`unknown` and is never inferred from the clock.

Result positions, points, lap counts, times and gaps are nullable when unavailable.
Durations and gaps use integer milliseconds. Points use decimal values with
three fractional digits; no float calculations are introduced. Grid position 0
denotes a pit-lane start; null denotes unavailable grid information.

Standings store explicit points, wins and positions after the referenced event,
not calculated values or season-only overwrites. Each snapshot is unique per
event/driver or event/team. A composite foreign key ensures that the event
belongs to the supplied season. Create schemas reject unknown fields and do not
accept application IDs or audit timestamps.

## Focused validation

These checks cover configuration, liveness, datetime validation, missing values,
domain integrity, migration reversal, and PostgreSQL SQL generation:

```powershell
apps/api/.venv/Scripts/python.exe -m unittest discover -s apps/api/tests -p test_phase1.py -v
apps/api/.venv/Scripts/python.exe -m ruff check apps/api/app apps/api/migrations apps/api/tests
apps/api/.venv/Scripts/python.exe -m ruff format --check apps/api/app apps/api/migrations apps/api/tests
```

The persistence tests run migrations on temporary in-memory SQLite and compile
PostgreSQL SQL. They do not establish a live PostgreSQL connection or substitute
SQLite for the application's configured PostgreSQL database.

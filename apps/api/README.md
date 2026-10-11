# Backend foundation, core ingestion and telemetry storage

Phase 1 adds configuration, PostgreSQL sessions, nine core models, Pydantic
create/read schemas, `/v1/health`, and the initial Alembic revision. Setup and
startup commands are in the [root README](../../README.md).
Phase 2 adds the Jolpica adapter, explicit core imports, provider identity mappings,
import metadata, read APIs, date-only schedule fields, and nullable standings ranks.
Phase 4 adds normalized session-data storage, historical OpenF1 imports, telemetry
read APIs, an immutable source-revision ledger, and deterministic tyre age.
Phase 5 adds a read-only lap-comparison service using these persisted records.
Phase 11 (prompt numbering) adds an explicit historical post-session worker.

## Historical seasons (V2 Phase 2)

From the repository root, import one additional season independently:

```powershell
$env:PYTHONPATH = "apps/api"
apps/api/.venv/Scripts/python.exe -m alembic -c apps/api/alembic.ini upgrade head
apps/api/.venv/Scripts/python.exe -m app.ingestion --season 2010
Invoke-RestMethod "http://localhost:8000/v1/seasons/2010/availability"
Invoke-RestMethod "http://localhost:8000/v1/events?season=2010&limit=200"
Invoke-RestMethod "http://localhost:8000/v1/drivers?season=2010&limit=200"
Invoke-RestMethod "http://localhost:8000/v1/standings/drivers?season=2010&limit=200"
Invoke-RestMethod "http://localhost:8000/v1/standings/constructors?season=2010&limit=200"
```

FastAPI must be running for the verification requests. Open `/races?season=2010`
in the web app. Repeat the import to apply source corrections without changing
domain UUIDs or duplicating records. `--season <YEAR> --round <ROUND>` remains
available for an independent weekend; there is no startup or automatic all-history
import. Existing 2025 imports continue unchanged. The existing provider paginates
at 100 records, paces requests and bounds retries; run season imports sequentially,
respecting [Jolpica's published rate limits](https://github.com/jolpica/jolpica-f1/blob/main/docs/rate_limits.md).

Migration `0008_historical_core_sources` adds private `core_source_revisions` and
`core_source_states`. Core raw collection snapshots are hashed and archived once
per changed source revision. An aware timestamp taken **before** provider requests
orders normalized updates under the existing provider transaction lock. Older
observations remain archived but cannot overwrite newer corrections; unchanged
observations advance the ordering watermark. Existing successful import metadata
provides a conservative ordering floor during migration. Earlier raw payloads
cannot be recovered and are not fabricated. No additional configuration is needed.

`GET /v1/seasons` lists persisted seasons with additive coverage fields. The
bounded `GET /v1/seasons/{year}/availability` also reports years not imported:

- `imported`: a successful whole-season core fetch, calendar, recorded race
  results for elapsed calendar dates, and both latest driver/constructor snapshots
  covering the elapsed rounds.
- `partial`: some calendar records exist, but the whole-season import or that
  core coverage is missing. Round-only imports and historical source gaps can
  leave this state, including years without constructor standings.
- `unavailable`: no imported calendar for that year; no provider request is made.

Counts and category availability are deterministic coverage calculations, not a
claim that every classification, qualifying time or session exists in the source.
The selector offers imported/partial years; an unavailable requested year never
silently falls back to another year. Driver lists use recorded season results and
standing membership; identity details remain shared, and results/teams/points are
season-scoped. APIs retain bounded `limit`/`offset` pagination and batch identities.

Historical weekends display only source-supplied sessions/classifications;
missing sprint, qualifying, practice or standings records stay unavailable. A
conflicting multi-car classification for the same driver/session cannot be
represented by the existing single-result contract, and is rejected atomically
rather than silently merged.

Core season imports do **not** import telemetry, register workers, or change
existing live scopes. A completed historical session cannot be registered with
`--live`; explicit historical post-session registration remains supported.
Telemetry Lab/Strategy use existing empty states unless OpenF1 records have been
separately imported. Pitwall receives the selected historical year/event/session
and uses the existing read-only tools and grounding/protection rules.

Operational review: apply the migration, import/rerun 2010, confirm availability
and both standing categories, inspect a race detail and driver profile, then check
Telemetry Lab/Strategy and a contextual Pitwall query report missing records.
No live model call is required by automated tests.

## Automatic post-session updates (Phase 11 prompt)

Run migrations first (`0004_session_updates`). The worker is a separate process,
never part of FastAPI or its reload processes. Existing core sessions/drivers must
be imported before registration. Reuse the explicit Phase 4 application UUIDs and
OpenF1 session/driver mappings; numbers alone are not permanent driver identities.

For the existing 2025 Australian race, after setting `$sessionId`, `$norrisId` and
`$verstappenId` as in the historical-import example:

```powershell
$env:PYTHONPATH = "apps/api"
apps/api/.venv/Scripts/python.exe -m alembic -c apps/api/alembic.ini upgrade head
apps/api/.venv/Scripts/python.exe -m app.workers --register --session $sessionId --source-session 9693 --driver "4=$norrisId" --driver "1=$verstappenId"
apps/api/.venv/Scripts/python.exe -m app.workers --once
apps/api/.venv/Scripts/python.exe -m app.workers --status --session $sessionId
```

For continuous background checks, run `python -m app.workers --watch` with the same
repository virtual-environment interpreter and `PYTHONPATH`. Stop with Ctrl+C.
Default checks are every 1800 seconds; `--poll-seconds` cannot be below 900.
Far-future sessions defer until the day before their scheduled start. Historical
sessions missing completion evidence or core publication wait at least six hours
between checks.
One PostgreSQL advisory lock prevents overlapping workers and is released on exit
or connection loss. A restarted worker re-runs interrupted jobs idempotently.

Each registered scope refreshes Jolpica schedule/results/available standing
snapshots (one import per event per tick). Telemetry finalization requires the
existing 30-minute historical settling window plus published classification or
an explicit OpenF1 session-end/track chequered signal. Qualifying chequered signals
and session-end signals require phase 3, avoiding Q1/Q2 completion guesses;
absent phase metadata waits for published classification. A later start/resume
supersedes older terminal signals. Date/time alone never confirms completion.
Source cancellation metadata/messages stop the job; scope mismatches fail safely.
Completion signals use the [OpenF1 race-control contract](https://openf1.org/docs/#race-control).

Finalization reuses Phase 2/4 normalization, validation, mappings and atomic
ingestion for supported results, laps, car data, stints, pits, positions/intervals,
race control and weather. Raw revisions, approximate lap-window labels, unknown
channels and tyre-age semantics are unchanged. Missing collections remain empty,
not invented. Published classification is not a claim of official finality;
later corrections can be re-imported with an explicit `--retry --session <UUID>`.
Jolpica-supported race/sprint/qualifying jobs remain pending while classification
is unavailable; race/sprint jobs also await event standings snapshots. Already
imported telemetry stays available while polling core publication, without repeated
full telemetry downloads. Once core data arrives, final ingestion runs again to
capture late source revisions. Unsupported practice results are never invented.

`session_update_jobs` records stages, attempts, completion evidence, linked import
runs, row counts and a versioned strategy calculation audit snapshot. Existing
APIs continue calculating current strategy/comparisons from application data;
they do not read this snapshot. Cache invalidation receives session/event/season/
driver scope, but currently records `not_cached`: APIs query the database and
Next.js uses `cache: no-store`, so no active data cache requires eviction.
Optional AI report generation is not enabled; interactive Pitwall is unchanged.

Dependency/validation failures back off by the polling interval, then twice that
interval. Three consecutive failures stop the job. Inspect `--status`, fix the
cause, then use `--retry --session <UUID>` to reset the failure count. Logs include
job/stage/count/duration and fixed error categories, never raw exception strings
or private configuration. No new dependencies or environment variables are needed.

Focused checks:

```powershell
$env:PYTHONPATH = "apps/api;apps/api/tests"
apps/api/.venv/Scripts/python.exe -m unittest test_phase11 test_phase2 test_phase4 test_phase7
```

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

## Telemetry data imports (Phase 4)

The [OpenF1 adapter](https://openf1.org/docs/) imports historical session data.
Provider capabilities and free access were checked on 2026-10-06: historical
coverage begins in 2023, and historical access requires no authentication.
The [free tier](https://openf1.org/) allows 3 requests/second and 30/minute;
this adapter spaces requests by at least 2.1 seconds and honors `Retry-After`.
It retries transport errors, HTTP 429 and server errors at most three times.
Long waits, other HTTP failures and malformed data fail the import. The provider's
specific 404 `No results found.` response is an empty optional collection, while
a missing source session is an error. There is no undocumented pagination scheme:
documented JSON collections are fetched per selected driver to bound response size.

### Local setup and identifiers

Import the matching Phase 2 core event first, then migrate from the repository root:

```powershell
apps/api/.venv/Scripts/python.exe -m alembic -c apps/api/alembic.ini upgrade head
# Example: ensure the 2025 Australian event and core driver catalog are present.
apps/api/.venv/Scripts/python.exe -m app.ingestion --season 2025 --round 1
$events = Invoke-RestMethod 'http://localhost:8000/v1/events?season=2025&limit=200'
$eventId = ($events | Where-Object round -eq 1).id
Invoke-RestMethod "http://localhost:8000/v1/events/$eventId/sessions"
Invoke-RestMethod 'http://localhost:8000/v1/drivers?limit=200'
# Read-only source discovery: inspect its session_key, dates, type and country.
Invoke-RestMethod 'https://api.openf1.org/v1/sessions?year=2025&country_name=Australia&session_name=Race'
Invoke-RestMethod 'https://api.openf1.org/v1/drivers?session_key=<openf1-session-key>'
```

Copy the application's matching session UUID and selected driver UUIDs from these
responses. Use OpenF1's **session car number**, not the driver's permanent number.
Import one or more explicitly mapped drivers:

```powershell
apps/api/.venv/Scripts/python.exe -m app.ingestion.telemetry --session <application-session-uuid> --source-session <openf1-session-key> --driver "<car-number>=<application-driver-uuid>"
# Repeat --driver "<another-number>=<another-driver-uuid>" to extend the scope.
Invoke-RestMethod 'http://localhost:8000/v1/sessions/<application-session-uuid>/laps?limit=200'
Invoke-RestMethod 'http://localhost:8000/v1/sessions/<application-session-uuid>/telemetry?driver_id=<application-driver-uuid>&limit=200'
```

Angle-bracket values are placeholders to replace. A full-session import can be
large; start with the drivers you need. Source sessions must have ended more than
30 minutes ago, outside OpenF1's live-access window. Session year/type, country and
scheduled date must match the existing domain session. Explicit driver mappings
are checked against available source/domain driver codes. Identity conflicts fail
rather than reassigning an existing mapping. Mappings are session-scoped so a car
number can represent a different driver in another session. Core models and
Jolpica identities are unchanged; OpenF1 session mappings reuse `provider_identities`.

### Persistence, provenance and source fields

`Lap`, `TelemetrySample`, `Stint`, `PitStop`, `PositionSample`, `IntervalSample`,
`RaceControlMessage` and `WeatherSample` reference existing session/driver UUIDs.
Provider/key uniqueness and natural constraints prevent duplicate samples on
retry. All timestamps use timezone-aware schemas and PostgreSQL timestamps;
source timestamp precision is retained. A composite lap foreign key prevents
associating a sample with another session, driver or provider.

Imports create an `import_runs` record linked to the domain season/session before
source IO. Requested driver numbers are included in its external scope identifier.
The normalized data, identity mappings, source revisions and success state commit
atomically under a PostgreSQL provider advisory lock. Serialization, deadlock and
unique conflicts retry the transaction at most three times using the fetched bundle.
Failures roll back data writes and record sanitized failure metadata separately.
An empty collection does not delete earlier data or certify source completeness.
Zero counts in `row_counts` identify collections absent from the selected import.

Raw record payloads are retained separately in `telemetry_source_records`, keyed
by provider, session, kind, source key and content checksum. Reimports reuse
identical revisions; corrected source values append revisions and update the
normalized row while preserving its UUID. Source rows are never updated by this
pipeline. `fetched_at` records retrieval, not an authoritative source-update time;
the latter remains null. Raw provider payloads and keys are excluded from read APIs.

Normalized source fields:

- Laps: number, approximate source start, duration and three sector durations in
  decimal seconds, pit-out state; unavailable values remain null.
- Telemetry: source timestamp, speed in km/h, throttle percentage, brake applied
  boolean, gear (including neutral 0), RPM and numeric DRS state. Brake 0/100 becomes
  off/on; its original numeric value remains in the raw ledger. DRS state is retained
  without guessing ambiguous codes. No pressure is derived from brake state.
  The upstream pedal value 104 indicates unavailable/error data: brake/throttle
  normalize to null for that value, while immutable source payloads retain 104.
  Other unsupported brake states and out-of-range throttle values still fail validation.
- Stints: number, compound, first/last lap and supplied tyre age at stint start.
- Pits: lap, timestamp, pit-lane duration and stationary stop duration separately.
  Deprecated `pit_duration` supplies lane duration only when the new value is absent.
  Missing stationary duration remains null, never replaced by pit-lane time.
- Positions: race/session classification position, not GPS coordinates.
- Intervals: decimal seconds or separately tagged lap counts for interval/gap.
  Null leader values stay null; lap gaps are never converted into time gaps.
- Race control: timestamp, message, category, flag, scope and available driver,
  lap, sector and qualifying-phase context. Messages for unmapped drivers are
  outside the selected scope; general messages are included.
- Weather: timestamp, air/track temperature in °C, humidity %, pressure mbar,
  rainfall state, wind direction degrees and wind speed m/s.

Microsector colors and speed-trap fields remain only in raw lap payloads.
Location, radio, overtakes, source standings and result endpoints are not imported.
There are no tyre temperatures/pressures, fuel loads, brake pressures or other
unsupported engineering channels in the application contracts.

OpenF1 documents lap-start times as approximate. Samples therefore retain
session/driver/time with **null `lap_id`**, and laps expose
`start_time_is_approximate=true`. Session telemetry reads return the traces;
lap-specific telemetry reads return only confidently associated samples, so they
are empty for this adapter. No timestamp-window guess or distance interpolation is
stored. Permanent lap association remains unresolved; Phase 5 can select explicitly
requested approximate windows for comparison without changing sample associations.

### Session-data read APIs and tyre age

All collection routes use the existing array, `limit` (1–200, default 50), `offset`,
404/empty/503 conventions. IDs are application UUIDs; `provider` supplies provenance.
Collections accept a provider filter, and driver collections accept `driver_id`.

- `GET /v1/sessions/{session_id}/laps`
- `GET /v1/laps/{lap_id}` and `/v1/laps/{lap_id}/telemetry`
- `GET /v1/sessions/{session_id}/telemetry`
- `GET /v1/sessions/{session_id}/stints`
- `GET /v1/sessions/{session_id}/pits`
- `GET /v1/sessions/{session_id}/positions`
- `GET /v1/sessions/{session_id}/intervals`
- `GET /v1/sessions/{session_id}/race-control`
- `GET /v1/sessions/{session_id}/weather`
- `GET /v1/stints/{stint_id}/tyre-age?completed_lap=13`

Session telemetry accepts aware `from_time` (inclusive) and `to_time` (exclusive).
It never calls upstream during a request. Decimal measurements serialize as strings,
consistent with existing domain decimal contracts.

Tyre age is separate **derived** data, formula version `completed-laps-v1`:
`usage = min(completed_lap, lap_end) - lap_start + 1`, omitting the minimum if
the source end lap is unavailable; `total_age = tyre_age_at_start + usage`.
`lap_start` is the first lap driven on the set: after `lap_start - 1`, usage is 0;
after `lap_start`, it is 1. Requests past a known end return the set's final age.
Missing starting tyre age yields null total age, never an assumed fresh set.
Missing start lap or requests before fitting return 422. The caller supplies the
completed-lap boundary; the calculation does not certify that the lap was completed.
Source stint rows remain unchanged.

### Focused Phase 4 checks

```powershell
apps/api/.venv/Scripts/python.exe -m unittest discover -s apps/api/tests -p test_phase4.py -v
```

Checks use temporary SQLite, mocked HTTP transport and PostgreSQL SQL generation.
They cover import identity, source revisions, transactions/retries, units/nulls,
API reads, lap scope integrity, migrations and tyre-age boundaries.
Phase 4 adds no comparison service, Telemetry Lab, scheduler, AI or replay.

## Lap comparison (Phase 5)

`POST /v1/telemetry/compare` compares two distinct application lap UUIDs from the
same session. It reads existing lap, telemetry and stint rows; it performs no
provider requests, ingestion, database writes or persistent sample reassignment.
No new dependencies, migration, UI, strategy feature, AI or replay are required.

```powershell
# Replace placeholders with two imported lap UUIDs from the same session.
$comparison = @{
  lap_a_id = '<application-lap-a-uuid>'
  lap_b_id = '<application-lap-b-uuid>'
  sample_count = 201
  alignment = 'normalized_distance'
  allow_approximate = $false
} | ConvertTo-Json
Invoke-RestMethod 'http://localhost:8000/v1/telemetry/compare' -Method Post -ContentType 'application/json' -Body $comparison
```

Request options:

- `sample_count`: 2–2001, default 201, including both grid endpoints.
- `alignment`: `normalized_distance` (default) or `elapsed_time`.
- `allow_approximate`: false by default. Set true explicitly for OpenF1 traces:
  Phase 4 stores null sample lap IDs and approximate lap starts.

The response includes both normalized lap summaries, source stint/compound context,
derived tyre ages, lap/sector deltas in milliseconds, synchronized channels, a
delta trace when supported, and method/availability/provenance metadata. Decimal
values serialize as strings, consistent with the existing API. Missing laps return 404. Invalid UUIDs, repeated lap IDs, different sessions, unknown fields, invalid
sample counts, or more than 50,000 eligible source samples per lap return 422.
Missing timing or telemetry returns a comparison with explicit unavailable values,
rather than fabricated measurements. Nonpositive timing values remain in the source
summary but do not participate in timing deltas or trace construction.

### Sample association and data classification

By default, comparison uses only samples already linked to each lap, scoped to its
session, driver and provider. An approximate start is also excluded unless the
caller opts in. When opted in, the service reads unassigned samples in the source
start/duration window, including up to one second of boundary context for
interpolation. Samples explicitly assigned to another lap remain excluded.
Eligible confirmed samples can be included in the same read. No `lap_id` is changed.

If either selected set uses approximate starts or unassigned samples, the trace is
classified as **estimate**, with `approximate_window` association metadata and a
warning. Otherwise, transformed traces are **derived**, never raw measurements.
Raw lap/sector times and source tyre metadata remain separate in the lap summaries.
Missing start/duration or no eligible samples leaves trace data unavailable; lap
and sector deltas remain usable independently when their own timing inputs exist.

### Alignment, interpolation and missing samples

`lap-comparison-v1` uses these rules:

1. For normalized distance, convert speed km/h to m/s and trapezoidally integrate
   it over elapsed lap time. The whole interval must have nonnull speed coverage,
   including both boundaries, without source-row gaps longer than one second.
   No distance is accumulated through missing data.
2. Normalize each lap's integrated distance independently to 0–1 and resample at
   `sample_count` equally spaced fractions. Invert each cumulative-distance curve
   with linear interpolation between knots to obtain elapsed times. Interior
   stationary plateaus use first arrival; fractions 0 and 1 retain source lap
   start/finish boundaries. This is derived distance, **not authoritative track
   position or GPS**, and independent distance normalization can stretch differences
   caused by measurement error or different racing lines.
3. If either speed curve is incomplete or has zero total distance, fall back to a
   common elapsed-time grid spanning the longer lap and report a warning. An
   explicit `elapsed_time` request uses this method directly. A shorter lap has
   null channel values after its finish. Elapsed-time alignment returns **no delta
   trace**: equal elapsed time does not establish equal track position.
4. Speed, throttle and RPM use linear interpolation between adjacent source rows.
   Brake state, gear and numeric DRS state hold the previous sample; they are never
   averaged into fictional states. Unknown DRS codes retain their original meaning
   as codes rather than being converted to guessed on/off states.
5. Do not extrapolate before the first sample or after the last. Do not bridge
   source-row gaps over one second. Explicit null continuous channels make
   interpolation unavailable across that interval; exact sampled nulls stay null.
   Discrete nulls remain unknown until a subsequent known sample. No missing sector
   time is inferred by subtracting other sectors from lap time.

The trace reports actual/requested alignment, axis, resolution, interpolation
methods, the gap threshold, eligible source counts, integrated distances where
available, warnings, and `available`/`partial`/`unavailable` channel-grid status.
Continuous resampling is reported to six decimal places. Distance-to-time inversion
uses microsecond precision; raw timestamp and channel values remain unchanged.

### Delta convention and tyre context

All timing deltas use `A - B` in milliseconds. A positive lap/sector delta means A
took longer; a negative one means A was faster. For distance-aligned points:
`delta_ms = (A_elapsed_seconds - B_elapsed_seconds) * 1000` at the same normalized
integrated-distance fraction. That reference is explicit and is not an official
position-gap measurement. Missing/nonpositive timing inputs produce null deltas.

Tyre context uses one unambiguous stint from the same session/driver/provider with
source start/end laps containing the selected lap. Missing/unknown boundaries or
overlaps return unavailable/ambiguous context; no compound or fresh tyre set is
guessed. Unknown `tyre_age_at_start` keeps total ages null while usage remains
calculable for a known stint. Reusing `completed-laps-v1`, a lap numbered `N` reports
age before it using completed lap `N - 1`, and after it using completed lap `N`.
For a set starting at lap 4 with source age 3, lap 10 has usage 6/7 and total age
9/10 before/after. The source stint is not modified.

### Focused comparison checks

```powershell
apps/api/.venv/Scripts/python.exe -m unittest discover -s apps/api/tests -p test_phase5.py -v
```

Tests use temporary storage and hand-calculated timings, speed integrals and tyre
ages. They verify endpoint validation, delta signs, variable speed, stationary
samples, channel interpolation, gaps, provider scope, missing data, approximate
selection and preservation of raw source revisions and sample associations.

## Strategy + Tyres (Phase 7)

`GET /v1/sessions/{session_id}/strategy` reads existing Phase 4 normalized laps,
stints, pits and race control. An optional `provider` filter uses the existing
provider convention. Missing sessions return 404; any session other than a
recorded completed race returns 422. Empty imports return empty collections,
never fabricated strategies. No migrations, ingestion changes or provider calls
are required. Raw source rows and revisions are unchanged.

Each driver/provider is separate. Source stints and pit stops retain the existing
read schemas. `lap_axis_end` is the largest imported lap/stint-end/pit-lap number,
not an official race distance. Safety-car/VSC context retains source messages
whose category/flag or explicit text mentions those controls, including associated
infringement messages. It does not infer complete deployment periods or team intent.

Tyre snapshots reuse `completed-laps-v1`: usage is
`age_completed_lap - lap_start + 1`, total age is source starting age + usage.
For complete unambiguous bounds, the snapshot is the source end lap. When stints
overlap, the snapshot is the last positive-duration recorded lap uniquely contained
by that stint. Shared laps are never reassigned. Incomplete bounds or no unambiguous
snapshot yield null ages/usage; unknown starting age yields null total age.
The response explicitly identifies the snapshot lap and source context status.

`observed-non-pit-v1` pace is the arithmetic mean and minimum of recorded lap
durations in each complete source stint. Eligible laps have positive duration,
source `is_pit_out_lap=false`, unique stint containment, and are neither source pit
laps nor the following lap. Unknown pit-out state is excluded. A pit with missing
lap number disables pace for that driver/provider. Missing stint boundaries that
could overlap disable ambiguous lap assignment. Counts identify recorded, included
and excluded laps; no eligible laps yield null metrics, not zero. Mean seconds
are rounded to six decimals. These are observed metrics affected by traffic and
neutralisations, not clean-air estimates or official lap-validity certification.
No tyre-health, degradation, fuel correction or strategy-intent model is added.

Focused temporary-database checks:

```powershell
apps/api/.venv/Scripts/python.exe -m unittest discover -s apps/api/tests -p test_phase7.py -v
```

## Pitwall backend (Phase 08)

`POST /v1/ai/query` uses the existing application handlers/services and public DTOs.
No F1 provider calls, ingestion writes, migrations, reports, frontend AI UI or 3D are
added. Configure **only** `apps/api/.env`, retaining the existing database settings:

```dotenv
GEMINI_API_KEY=<server-only-key>
PITWALL_PROVIDER=gemini
PITWALL_MODEL=gemini-3.8-flash
PITWALL_FALLBACK_MODELS=gemini-3.7-flash,gemini-3.6-flash
PITWALL_MAX_RETRIES=1
```

Blank/unset AI values leave the data APIs operational; queries return 503 until
configured. Restart the API after changing environment configuration. Never put
the key in `NEXT_PUBLIC_*`, client code, requests or committed files. Keys are
masked in settings and upstream failures return fixed public-safe messages.
SDK payload logging is suppressed even when `GOOGLE_GENAI_DEBUG` is enabled.
Gemini uses the official `google-genai` Python SDK's
[Interactions function-calling](https://ai.google.dev/gemini-api/docs/function-calling)
and [structured-output](https://ai.google.dev/gemini-api/docs/structured-output)
contracts. `gemini-3.8-flash` is listed as stable in Google's current
[model catalog](https://ai.google.dev/gemini-api/docs/models), with free-tier
input/output listed in the [pricing documentation](https://ai.google.dev/gemini-api/docs/pricing).
Free-tier quotas and project availability still apply; free-tier content may be
used to improve Google's products. Only public application evidence and the
question/context are sent; no keys go in prompts or tool content.

The provider factory retains OpenAI: set `PITWALL_PROVIDER=openai`,
`OPENAI_API_KEY` locally, and an appropriate `PITWALL_MODEL`. Blank/unset provider
preserves the existing OpenAI default. Gemini model fallback stays within Gemini;
there is no fallback between providers. The optional comma-separated model list
is tried in order, with duplicates removed and at most three fallback models.
Google currently lists `gemini-3.7-flash` and `gemini-3.6-flash` as stable models
with function calling, structured outputs and free-tier input/output.

Gemini retries transient 429/500/502/503/504 and transport failures. One retry per
model is the default; `PITWALL_MAX_RETRIES` accepts 0-2, with delays of 1s then 2s.
Retries/fallbacks share a 45-second budget across all model turns in one query;
request timeouts are capped by the remaining budget. A successful fallback is
retained for the query. Authentication, malformed requests and identified daily,
zero or exhausted quotas stop immediately. Unknown 429 rate limits remain bounded.
If all attempts fail, the existing public-safe 503 response is preserved.
Logs contain only safe model IDs, status categories, retry counts and decisions;
provider error bodies, keys and prompts are never logged.
OpenAI uses existing `httpx` and the official
[Responses function-calling](https://developers.openai.com/api/docs/guides/function-calling)
and [structured-output](https://developers.openai.com/api/docs/guides/structured-outputs)
contracts. Both providers set `store=false`. Gemini replays the full native model
steps, including opaque thought signatures, and function results statelessly.
Thoughts and provider payloads are never exposed in the public answer. Only the
existing application tool registry executes functions; no SDK automatic function
execution, built-in search/code tools or implicit SDK retries are enabled.

Example from the repository root with the API running on port 8000:

```powershell
$sessionId = '<application-session-UUID>'
$body = @{
  question = 'Explain the recorded stints and observed pace; distinguish evidence from interpretation.'
  context = @{ route = '/strategy'; session_id = $sessionId }
} | ConvertTo-Json -Depth 6
Invoke-RestMethod -Method Post -Uri 'http://localhost:8000/v1/ai/query' -ContentType 'application/json' -Body $body
```

Context supports optional `route`, `season` (year), `event_id`, `session_id`,
`driver_id`, `lap_id`, `stint_id`, `comparison` (the Phase 5 compare request), and
`allow_approximate`. IDs must be stable domain UUIDs. IDs and relationships are
validated before contacting the model; missing/inconsistent context returns 422.
Route text is descriptive, never silently parsed to select an event. When IDs are
absent the model must retrieve candidate application records before answering.

Read-only tools cover drivers, events/sessions, results, laps, confirmed/source
telemetry, stints/tyre age, pits, positions, intervals, driver/constructor standings,
race control, weather, completed-race strategy, and lap comparison. List tools
return at most 200 records with explicit `truncated`/`next_offset`; comparison
is capped at 201 points. Approximate-window comparison requires explicit user
opt-in through context, including `context.comparison.allow_approximate`.
Queries are bounded to six model rounds, twelve model tool calls and a checked
60-second orchestration budget; each upstream request has a 20-second HTTP timeout.
Oversized tool results are explicitly unavailable and require a narrower query.

Responses separate `facts` (source), `calculations` (deterministic derived values),
`estimates`, `interpretations`, `unavailable`, and `evidence`. Facts, calculations
and estimates contain evidence IDs/JSON pointers and **server-resolved scalar
values**; the model cannot supply their values or invent arithmetic. Approximate
lap starts and comparison traces stay in `estimate`; interpolated confirmed
traces are `derived`. Delta signs and tyre ages reuse the Phase 5/7 contracts.
Evidence contains normalized DTOs with nulls intact, never raw provider payloads.
Unavailable fields, empty imports, page limits and missing channels are explicit.
Interpretations select a bounded kind (observed pace, pit timing, tyre context or
lap comparison) and cite relevant evidence. The server checks the required data
and supplies fixed uncertain wording; arbitrary model prose is rejected, including
numeric words or unsupported claims hidden in explanations. These are analytical
caveats, not verified causality or confirmed team intent.

Invalid/unreferenced/misclassified answers or exhausted call budgets return 502,
without a model-memory fallback. Database/model unavailability returns 503. No
paid model call occurs in tests; retry/fallback behavior uses controlled transport:

```powershell
apps/api/.venv/Scripts/python.exe -m unittest discover -s apps/api/tests -p test_phase8.py -v
apps/api/.venv/Scripts/python.exe -m unittest discover -s apps/api/tests -p test_gemini.py -v
```


### Near-live session updates (V2 Phase 1)

Stop workers before applying `alembic upgrade head`; migration
`0007_near_live_updates` adds opt-in state to existing update jobs. No raw telemetry
or F1 domain columns change. Existing registrations remain historical-only.

OpenF1 live REST access requires a paid subscription and server-side
`OPENF1_USERNAME` / `OPENF1_PASSWORD` in `apps/api/.env` (see the
[official authentication guide](https://openf1.org/auth.html)). Tokens are renewed
before hourly expiry; credentials and tokens are never returned by application APIs.
Historical finalization remains unauthenticated and works without live access.

From the repository root in PowerShell, reuse the existing domain UUIDs, source
session key and driver mappings from the historical registration instructions:

```powershell
$env:PYTHONPATH = "apps/api"
apps/api/.venv/Scripts/python.exe -m alembic -c apps/api/alembic.ini upgrade head
apps/api/.venv/Scripts/python.exe -m app.workers --register --live --session $sessionId --source-session $sourceSession --driver "4=$norrisId" --driver "1=$verstappenId"
apps/api/.venv/Scripts/python.exe -m app.workers --watch
# In another terminal with the same PYTHONPATH:
apps/api/.venv/Scripts/python.exe -m app.workers --status --session $sessionId
Invoke-RestMethod "http://localhost:8000/v1/sessions/$sessionId/updates"
```

`--live` can enable an existing idle registration with the same immutable scope.
Registration stays explicit: no calendar-wide discovery or automatic driver mapping.
`SESSION_LIVE_POLL_SECONDS` (or `--live-poll-seconds`) is bounded to 60-300 seconds.
The interval starts after each cycle's IO. A connection-owned PostgreSQL worker lock
prevents overlapping workers and releases on crash. Requests are paced at 1.1s
for authenticated live access (60/minute limit) and 2.1s for public historical
access (30/minute limit), with at most three transient attempts and bounded
Retry-After waits. Live registrations support up to 32 explicitly mapped drivers.

An active session requires session-level start/resume/green evidence or recent
source telemetry from a registered driver, within a six-hour window, not just a
scheduled time. Recent samples never override a source stop/end/cancellation. Timed streams use a maximum five-minute
catch-up window plus a two-minute overlap; the first observation covers the last
two minutes. Mutable lap/stint summaries and race-control history are rechecked, retaining
the source evidence used for detection. Repeated payloads produce
no new raw revision or normalized payload rewrite; their ordering watermark still
advances to prevent stale A-to-B-to-A restoration. Live row counts report changed rows.
The cursor, revision ledger and normalized data commit atomically. Late corrections
outside the overlap and missed earlier history remain provisional until the final
full refresh. Empty collections/nulls remain explicit; no channels are fabricated.

After three failed live cycles, live polling pauses (`live_suspended=true`) while
historical finalization remains scheduled, with its own fresh retry budget. The
last source end plus 30 minutes controls handoff; an unknown end uses a conservative
six-hour window from the scheduled start. Both remain only scheduling hints: the
original completion checks still decide finalization. `--retry --session $sessionId` re-enables
bounded attempts; stop the watch process first, or retry when it releases the lock.
Ctrl+C stops the local worker safely. Failed refreshes retain the last committed
cursor and data; a replacement worker resumes without a partial commit.

Session API responses add `updates`; `/v1/sessions/{id}/updates` returns only public
operational metadata. Consumers must check `data_status` (`not_tracked`,
`provisional`, `finalized`) alongside telemetry/lap data. Provisional records are
never final classification: the results endpoint withholds classification while
provisional. Pitwall evidence carries the same application-controlled status and
retains existing aggregate usage/concurrency protection.

Once the source is historical (30 minutes after the supplied end), the original
completion-evidence/results/standings checks and **full** telemetry import run.
Only a successful complete finalization changes the state to `finalized`; missing
results or provider failures leave it provisional. Race, Telemetry and Strategy
pages show that state and provide manual refresh. No WebSockets, client polling,
automatic Pitwall calls, or live strategy intent/replay inference are introduced.
## Saved Comparisons (V2 Phase 4)

Saved presets contain only versioned application IDs and selector settings, not
telemetry copies, calculations or AI answers. Supported types are `telemetry_laps`
and `strategy_tyres`: current driver/race profiles have no independent reusable
comparison state. Telemetry retains both lap/driver IDs, alignment and explicit
approximate-window opt-in; the existing UI's 201-point sampling stays unchanged.
Strategy retains both recorded driver/source selectors. Existing analysis APIs
remain authoritative for channel gaps, tyre age, pace and provenance.

From the repository root, with the existing database configured:

```powershell
apps/api/.venv/Scripts/python.exe -m alembic -c apps/api/alembic.ini upgrade head
apps/api/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir apps/api --reload --port 8000
```

Migration `0009_saved_comparisons` follows `0008_historical_core_sources`. It adds
only the presets table, domain foreign keys and owner/date/season indexes. Foreign
keys use `SET NULL` on deletion; original IDs remain in the configuration snapshot.
Deleting a preset never removes F1 records. No automatic migration runs at startup.

Temporary ownership is a **server-controlled local workspace UUID**, default
`00000000-0000-0000-0000-000000000001`. Deployments can set
`SAVED_COMPARISONS_OWNER_ID` to another UUID server-side. Requests cannot select
an owner and all CRUD is scoped to this namespace. This is shared local/single-user
storage, not multi-user authentication; no account/profile is created. Phase 5
can add a real user foreign key and explicitly claim/migrate workspace presets
without replacing their UUIDs or configurations. Changing the workspace value
isolates a namespace; it does not delete existing presets.

REST contracts:

- `POST /v1/comparisons`: `{title, comparison_type, configuration}` (201).
- `GET /v1/comparisons?season=2025&limit=50&offset=0`: bounded list (max 200).
- `GET /v1/comparisons/{uuid}`: current context, safe notices and reopening URL.
- `PATCH /v1/comparisons/{uuid}`: nonempty title and/or same-type configuration.
- `DELETE /v1/comparisons/{uuid}`: remove preset (204).

Writes reject malformed IDs, unknown settings/types, cross-season/session/lap
references and unrecorded strategy selectors. Reads batch identity resolution and
recheck records. Missing records or unsupported stored versions return an explicit
`unavailable` preset with no reopening URL; no replacement is selected. Partial
timing/confirmed channel coverage and provisional sessions remain labelled.
Strategy coverage is conservatively marked partial pending the existing strategy
page's detailed checks. Core season imports alone never imply telemetry exists.

`/comparisons/{uuid}/open` revalidates with the backend and redirects to the existing
`/telemetry` or `/strategy` query URL, restoring the original season/event/session
and exact pair. Those pages recompute through their existing APIs and preserve
their grounded Pitwall context. The list can filter by season or show all seasons,
and offers rename and confirmed deletion. There is no replay/authentication change.

Focused checks:

```powershell
apps/api/.venv/Scripts/python.exe -m unittest discover -s apps/api/tests -p test_v2_comparisons.py
node --experimental-strip-types --test apps/web/tests/comparisons.test.mjs
```

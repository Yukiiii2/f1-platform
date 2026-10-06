# Core frontend, Telemetry Lab, Strategy and Pitwall

Run `npm run dev:web` from the repository root after `npm install`. Configure
`NEXT_PUBLIC_API_URL` in `apps/web/.env.local` as the application API base address,
without `/v1`. It defaults to `http://localhost:8000`; it must be reachable from
the Next.js server. The browser does not call Jolpica or the application API.

Pages use Phase 2 read schemas and domain UUIDs, with fresh server-side reads.
The existing API and database schema require no frontend-specific changes.
Start the API, apply its migrations, and import records as described in the
[root setup guide](../../README.md) to populate the UI.

| Route                                                   | Behavior                                                              |
| ------------------------------------------------------- | --------------------------------------------------------------------- |
| `/`                                                     | Next scheduled event, or latest calendar event; championship previews |
| `/races?season=2025`                                    | Imported season calendar                                              |
| `/races/<event UUID>?session=<session UUID>`            | Schedule and selected session classification                          |
| `/drivers?q=<name or code>`                             | Search across the persisted driver directory                          |
| `/drivers/<driver UUID>?season=2025&event=<event UUID>` | Identity, latest season standing, selected weekend results            |
| `/standings?season=2025&view=drivers`                   | Latest driver snapshot                                                |
| `/standings?season=2025&view=constructors`              | Latest constructor snapshot                                           |
| `/telemetry?season=2025`                                | Weekend/session/lap selection and backend telemetry comparison        |

The newest imported season is selected by default. A requested season that has
not been imported displays an empty state. Lists follow API pagination until all
records are read. Snapshot captions identify the source event; categories can
have different latest snapshots. Driver directory membership does not imply a
current season entry or team assignment.

Only supplied fields are presented. Missing ranks, numbers, points and timing
remain unavailable. Source schedule times are formatted in UTC; date-only
records explicitly say the time is unavailable. Calendar selection uses dates
for navigation and never infers live or completed status from the clock.
Qualifying shows classification without inventing lap times. Result gaps in
milliseconds are formatted as seconds, not as total race durations.

The shared shell includes navigation, a skip link, visible focus, semantic tables,
scrollable table regions, and responsive layouts. Route loading uses static
skeletons; failed reads use a retry boundary; missing UUIDs use a not-found page.
The Telemetry Lab adds stored historical lap comparison. Strategy adds completed-race
stint comparison. Pitwall adds contextual analysis. No authentication, live updates,
or 3D is included.

## Pitwall frontend (Phase 09 prompt)

`/pitwall` links to the race, driver, Telemetry Lab and Strategy pages, each with
an inline Ask Pitwall section. Current validated domain IDs, season and route are
passed as structured context; Telemetry Lab also supplies the applied comparison
and its explicit estimated-window permission. Change the page selection before
asking about another context. Strategy queries attach the displayed driver names
and domain references to the question because the context contract has only one
driver field; the backend retrieves the session's strategy records. These selection
references are ordinary query data, not instructions to override grounding.

A same-origin server action posts to the existing `/v1/ai/query` contract. No model
configuration or secrets enter browser code. Responses render source data,
calculations, estimates, interpretation, citations and unavailable fields separately.
Evidence coverage remains explicit. Requests show a retrieval/analysis message
without claiming unreported intermediate progress. Rate limits and service failures
preserve the question for manual retry; context changes clear answers and ignore
in-flight results. Questions and answers are not persisted in browser storage.

Focused contract, display and transport checks:

```powershell
node --test apps/web/tests/pitwall.test.mjs apps/web/tests/core.test.mjs apps/web/tests/telemetry.test.mjs apps/web/tests/strategy.test.mjs
```

## Strategy + Tyres (Phase 7)

Open `/strategy?season=2025`, load a race weekend, and compare one or two imported
driver/provider records. Race detail also links to this view when the recorded race
status is completed. Season/race changes clear downstream selections. The server
consumes `/v1/sessions/{id}/strategy`; all age and pace calculations stay in the
backend. Existing loading, retry and not-found boundaries cover core data reads.

Timelines share an inclusive source lap axis. Compounds remain text-labelled;
source overlaps occupy separate lanes. Stint/pit/race-control links and detail
tables work with the keyboard. Small screens scroll inside the labelled timeline
and table regions. Source pits without lap numbers remain in the table without an
invented marker. Multiple race-control messages on one lap share an `RC+` marker;
all original messages remain listed. No deployment interval or pit intent is inferred.

Source starting tyre age stays separate from calculated usage/total age. Each age
states its completed-lap snapshot, which may precede the reported stint end when
source bounds overlap. Unknown starting age is unavailable. Observed non-pit pace
shows coverage and caveats; it includes traffic and neutralisations, and does not
claim clean-air pace, degradation or tyre-health percentages. See the
[API policies](../api/README.md#strategy--tyres-phase-7).

Focused display/selection checks:

```powershell
node --test apps/web/tests/strategy.test.mjs
```

## Telemetry Lab (Phase 6)

Choose an imported season, load a weekend, then load a session. The lab reads all
pages of `/v1/sessions/{id}/laps` and resolves the recorded drivers through the
existing domain API. Select a driver and recorded lap on each side, then compare.
Two different laps from the same driver are supported. Changing the season,
weekend, or session clears downstream selections. Comparisons can be bookmarked
or shared through the page URL; driver changes clear their selected lap.

The Next.js server sends `POST /v1/telemetry/compare`. The browser only receives
normalized comparison data; it never calls a provider or recomputes alignment,
timing deltas, or tyre ages. Core Jolpica results alone do not populate the lab:
historical OpenF1 data must first be imported through the existing Phase 4 job.
See the [API guide](../api/README.md) for import and comparison policies.

Estimated lap windows are disabled by default. Enable them explicitly for
OpenF1 laps whose starts are approximate. Result traces show **Estimate** whenever
the comparison API classifies them that way. Lap/sector timing and source tyre
metadata stay separate from calculated deltas and completed-lap tyre ages.
Unknown starting tyre age remains unavailable, never zero.

Charts consume the backend's synchronized grid: straight segments for speed,
throttle, RPM and delta; previous-state steps for brake, gear and DRS. DRS displays
source codes, without guessing their on/off meaning. Null points break paths,
including missing channels, with dots preserving isolated available samples.
No smoothing or extrapolation is performed in the browser. Both laps share the
same axis and cursor; use the slider with arrow keys or point at a chart to read
selected values. Solid/dashed lines and A/B labels complement color. SVG geometry
resizes with the page while axis labels remain readable HTML text.

Normalized integrated distance is labelled as calculated distance, not GPS or
authoritative track position. Elapsed-time alignment and the API's fallback
display seconds and explicitly omit the delta trace. A positive timing delta is
A slower, a negative one A faster, using A − B in milliseconds. Missing timing,
channel gaps, empty sessions, approximate opt-in requirements, and retryable API
errors have explicit states. Results identify the selected event, session,
drivers, laps, providers, tyre compound/age and alignment basis.

Focused Phase 6 checks:

```powershell
node --test apps/web/tests/telemetry.test.mjs
```

These use temporary HTTP responses and hand-checked chart geometry. No fixture
data is used by production pages. Backend ingestion, schema and comparison
policies are unchanged.

The Barlow Condensed display face is self-hosted from the
[Google Fonts source](https://github.com/google/fonts/tree/main/ofl/barlowcondensed)
under its bundled [SIL Open Font License](public/fonts/OFL.txt). No font service
request is needed at runtime. UI styles extend `DESIGN.md` and
`DESIGN_GUIDELINES.md` without changing their direction.

Focused checks (repository root, Node.js 22.18+ or 24+ for native TypeScript tests):

```powershell
node --test apps/web/tests/core.test.mjs
node node_modules/typescript/bin/tsc --noEmit --incremental false -p apps/web/tsconfig.json
```

The tests exercise the API reader against a temporary local HTTP server,
pagination, error handling, unavailable fields, date-only schedules, fractional
points, and imported season selection. They do not require a database or Jolpica.

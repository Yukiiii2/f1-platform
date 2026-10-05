# Core frontend — Phase 3

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
No telemetry, AI, authentication, live updates, or 3D is included.

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

# V2 Phase 3: Multi-car timing/order replay

Goal: replay persisted race/sprint order across multiple drivers, without inventing track coordinates, incidents or retirement timestamps. Extend the established race detail flow with `/races/[eventId]/replay` and a bounded read-only API.

Representation: timing/order lanes, not a circuit map. Position is discrete source data. Playback uses a labelled previous-sample hold for at most 30 seconds; after that the position is unavailable. No numeric interpolation of ranks or fabricated coordinates. Lap windows use only recorded starts + durations (approximate starts remain estimates). Pit windows exist only when a source lane duration exists. Missing team/retirement data stays null.

API: `GET /v1/sessions/{session_id}/replay`, selected single provider, max 32 drivers and max 600 position/interval samples per driver, bounded lap/pit/race-control context. SQL window downsampling keeps first and latest source samples per time bin. No raw telemetry rows or provider fetches. Capability needs at least two drivers with multiple distinct valid timestamped position records over overlapping coverage; gaps, incomplete grid, provisional or truncated records make it partial. Results alone never enable replay.

UI: dedicated server route resolves event/session/year; replay data fetched only on that route. Native controls (paused initially), 0.5/1/2/4x, scrub, restart, toggles and driver focus. Source time and held/unavailable state accompany order. Existing tokens, typographic hierarchy, tables and focus behavior; no 3D modifications. Session-scoped Pitwall uses existing tools/context and protections.

- [x] Failing backend tests for capability, gaps, bounds, identities, provisional and API behavior.
- [x] Replay schemas/service/API; source-preserving bounded sampling.
- [x] Failing frontend tests for playback, gaps, URL context, controls and unavailable states.
- [x] Replay route/components/helpers/CSS and race-detail entry point.
- [x] Focused regressions, lint/format/diff checks and independent review.
- [x] Documentation, verification record and limitations; no commit/push or V2 Phase 4.

## Changed files

- Backend: `apps/api/app/api/replay.py`, `apps/api/app/api/router.py`, `apps/api/app/schemas/replay.py`, `apps/api/app/services/replay.py`, `apps/api/tests/test_v2_replay.py`.
- Frontend: `apps/web/app/_lib/api.ts`, `apps/web/app/_lib/replay.ts`, `apps/web/app/_lib/replay-contracts.ts`, `apps/web/app/_components/race-replay.tsx`, `apps/web/app/races/[eventId]/page.tsx`, `apps/web/app/races/[eventId]/replay/page.tsx`, `loading.tsx`, `error.tsx`, `replay.css`, `apps/web/tests/replay.test.mjs`.
- Documentation: `README.md`, this plan/verification record. No models, migrations, configuration, ingestion, worker, provider, secret or decorative 3D files changed.

## Verification and limitations

Final validation: 136 selected backend tests passed with PostgreSQL opt-in enabled (replay, Phases 2/4/5/7/8/11/12, near-live and historical seasons), and 44 selected frontend tests passed (replay, historical context, telemetry, strategy, Pitwall and Phase 12). Scoped Ruff, Ruff format, ESLint, Prettier and `git diff --check` passed. No full build or unrelated suite was run.

Tests use isolated fixtures. PostgreSQL sampling and existing migration/worker checks use disposable schemas; application records and migrations are not changed. Coverage includes actual sample overlap (not only min/max envelopes), late first samples, exact hold boundary, grid/sample bounds, source context, historical results-only unavailability, provisional data, API validation, native control wiring, no autoplay, gap expiration and deterministic URLs. The independent review's coverage and marker-containment findings were reproduced and fixed.

The running local Australian GP API returns `partial`, two imported drivers and 9302.635 seconds of coverage. The replay route returns HTTP 200 and renders Norris/Verstappen, paused controls, source/quality notes and the partial notice. No additional data was imported. A full grid requires explicit imports of recorded position data for additional drivers. Browser automation inventory is empty, so screenshot/mobile visual verification remains pending. Scoped TypeScript diagnostics are confined to the pre-existing corrupted `node_modules/csstype/index.d.ts` (TS1490 and two TS1005 errors); dependency repair is outside this phase.

Replay snapshots do not poll during playback. The existing provisional-session refresh control loads newer records and authoritative worker finalization remains unchanged. Rank holds never exceed 30 seconds, do not extend backward, and are not coordinate interpolation. Missing pit duration/lap start/retirement state remains unavailable. Six-hour coverage and documented collection bounds limit payloads; downsampling can omit changes and can introduce explicit gaps. A detector warning about the small marker's colored border is intentional driver identity decoration, not a card accent.

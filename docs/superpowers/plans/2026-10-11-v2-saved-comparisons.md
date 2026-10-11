# V2 Phase 4 — Saved Comparisons

Persist configurations for existing telemetry lap and strategy driver comparisons, not analytical snapshots or AI answers. Reuse domain UUIDs, existing application APIs, query selectors and design tokens. Driver/race profile pages do not have actual comparison states and receive no save button.

Ownership: server-controlled local workspace UUID, never supplied by requests. No account table or authentication. Phase 5 can add a user FK and attach workspace presets by an explicit claim/migration, retaining IDs/configurations. This is local single-user storage, not a multi-user authorization boundary.

Storage: new saved_comparisons table/migration after 0008, indexed owner/update time and season. Nullable SET NULL domain FKs plus a versioned, typed configuration retaining original IDs allow deleted records to be reported without substituting another selection. Writes validate existence and event/season/session/driver/lap scope. Routes/types/settings are allow-listed. Responses recheck availability and batch identities. CRUD /v1/comparisons is ownership-scoped.

Frontend: /comparisons list with open, rename/edit title and delete controls. Save actions only on actual selected telemetry/strategy comparisons. Same-origin server actions delegate to FastAPI; no direct database/provider access. /comparisons/[id]/open revalidates server state before redirecting to existing deterministic query URLs; missing refs show an explicit empty state. Existing comparison pages handle partial channels/source windows and remain authoritative for calculations and Pitwall context.

- [x] Failing backend CRUD/validation/ownership/stale-data tests, then passing implementation.
- [x] Model, schema, migration, service, router and local ownership configuration.
- [x] Failing frontend save/open/manage/navigation tests, then passing implementation.
- [x] Existing-feature save actions and saved-comparison routes/components.
- [x] PostgreSQL migration consistency, focused regressions, scoped lint/format checks and independent code review.
- [x] Operational documentation and verification record. No secrets, authentication, replay changes, commit or push.

## Verification

Relevant backend regressions include telemetry ingestion/comparison, strategy,
Pitwall protections, historical seasons, near-live workers and replay. Isolated
PostgreSQL schemas verify model/migration parity and migration roundtrips.
Existing migration tests were extended for revision 0009 while retaining the
historical observation-backfill check.

Results: 120 selected backend tests passed, then all 10 saved-preset tests passed
after adding explicit real-but-wrong driver/session and mixed-source rejection
coverage. All 66 selected frontend tests passed, including eight preset tests.
Scoped Ruff, Ruff formatting, ESLint and Prettier checks passed. Git diff and
new-file whitespace checks passed. Independent code review and design-system
documentation inspection found no material issues; no durable design tokens or
adjacent design documents were changed.

Local database upgraded from 0008 to 0009 only; Alembic check reported no new
operations. Live REST CRUD and server reopening succeeded for both imported 2025
Australian GP comparison types. Both temporary verification presets were removed;
F1 records and local secrets were unchanged. Saved-list, Telemetry Lab and Strategy
HTTP checks returned 200. Real browser layout/keyboard review remains manual.

Scoped TypeScript diagnostics are blocked by the pre-existing binary-corrupted
node_modules/csstype/index.d.ts (TS1490/TS1005); dependencies were not modified.
The Impeccable detector returned no findings. Independent code/CSS review found
no material issues, without claiming screenshot-based approval.

## Files changed in this phase

- README.md; apps/api/README.md
- apps/api/app/models/comparisons.py; apps/api/app/models/__init__.py
- apps/api/app/schemas/comparisons.py
- apps/api/app/services/comparisons.py
- apps/api/app/api/comparisons.py; apps/api/app/api/router.py
- apps/api/app/core/config.py
- apps/api/migrations/versions/0009_saved_comparisons.py
- apps/api/tests/test_v2_comparisons.py; apps/api/tests/test_phase4.py; apps/api/tests/test_v2_history.py
- apps/web/app/_lib/saved-comparison-contracts.ts; apps/web/app/_lib/saved-comparisons.ts; apps/web/app/_lib/api.ts
- apps/web/app/_components/save-comparison.tsx; apps/web/app/_components/navigation.tsx
- apps/web/app/comparisons/page.tsx; apps/web/app/comparisons/actions.ts
- apps/web/app/comparisons/manage-comparisons.tsx; apps/web/app/comparisons/comparisons.css
- apps/web/app/comparisons/[comparisonId]/open/page.tsx
- apps/web/app/telemetry/page.tsx; apps/web/app/strategy/page.tsx; apps/web/app/globals.css
- apps/web/tests/comparisons.test.mjs
- docs/superpowers/plans/2026-10-11-v2-saved-comparisons.md

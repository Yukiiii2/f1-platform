# V2 Phase 2 Historical Seasons

Goal: browse only persisted historical season data through existing routes, retaining UUIDs, grounding, telemetry semantics and worker safety.

Architecture: reuse the season/round Jolpica CLI and normalized services. Add private raw core revisions and per-identity observation ordering under the existing provider transaction lock. Derive public availability in batched queries; scope driver membership by recorded results/standings. Carry explicit year URLs throughout existing navigation and page links.

Constraints: no automatic bulk history/telemetry, no dependencies, no secrets, no commits/push, no V2 Phase 3. Existing older records retain IDs and are not claimed to have retroactive raw evidence.

- [x] Core provenance, stale import protection and historical normalization tests.
- [x] Availability, season-scoped driver API and multi-season/API tests.
- [x] Existing frontend season selectors, links, navigation and Pitwall context; frontend tests.
- [x] Historical/live worker regression and migration/model consistency.
- [x] Document independent season import and operational verification.
- [x] Focused regressions, scoped Ruff/ESLint/format/diff checks and final review.

Review focus: missing constructor/qualifying/sprint history remains unavailable; complete fetch does not guarantee exhaustive source records; old fetch finishing last cannot erase corrections; unchanged imports retain UUIDs/raw revisions; completed historical sessions never enter live polling; changing year discards incompatible event/session/lap selections.

## Verification and review

- 122 focused backend tests passed (history, V2 live, workers, core ingestion/API, telemetry ingestion/comparison, strategy, Pitwall and Phase 12 protections).
- 43 frontend tests passed (history, core, Pitwall, telemetry, strategy, live notices and Phase 12).
- Disposable PostgreSQL migration upgrade/downgrade/re-upgrade and model comparison passed; existing observation backfill checked. No application migration/data changes.
- Scoped Ruff check/format, ESLint, Prettier and git diff --check passed.
- Scoped TypeScript check blocked by exactly three pre-existing diagnostics in corrupted node_modules/csstype/index.d.ts; no application diagnostics.
- Live Jolpica 2010 fetch normalized and imported twice into a disposable in-memory database: 19 events, 912 classifications (race + qualifying), 27 drivers, one raw revision, zero worker jobs; availability imported. No persistent application data changed.
- Independent read-only reviewer found one unavailable-year Pitwall entry link dropping year. Reproducing rendering test failed, then passed after links retained validated requested year and displayed NoSeason. No findings deferred.
- Existing source request pacing/pagination retained, confirmed against official Jolpica docs. Existing dependencies and local secrets untouched.

Commands:

```powershell
$env:PYTHONPATH = "apps/api;apps/api/tests"
$env:F1_TEST_POSTGRES = "1"
apps/api/.venv/Scripts/python.exe -B -m unittest test_v2_history test_v2_live test_phase11 test_phase2 test_phase4 test_phase5 test_phase7 test_phase8 test_phase12
node --test apps/web/tests/history.test.mjs apps/web/tests/core.test.mjs apps/web/tests/pitwall.test.mjs apps/web/tests/telemetry.test.mjs apps/web/tests/strategy.test.mjs apps/web/tests/live.test.mjs apps/web/tests/phase12.test.mjs
```

Operational review remains: apply migration0008 to application PostgreSQL, import/rerun 2010 using documented CLI, review selected-year pages and missing telemetry, optionally test a grounded historical Pitwall query. Early conflicting multi-car classifications fail safely; missing historical source categories remain partial/unavailable. No commit/push or V2 Phase 3.

## Files changed

- `README.md`
- `apps/api/README.md`
- `apps/api/app/ai/tools.py`
- `apps/api/app/api/core.py`
- `apps/api/app/ingestion/contracts.py`
- `apps/api/app/ingestion/service.py`
- `apps/api/app/models/__init__.py`
- `apps/api/app/providers/jolpica.py`
- `apps/api/app/providers/jolpica_normalization.py`
- `apps/api/app/schemas/domain.py`
- `apps/api/app/services/core.py`
- `apps/api/app/workers/sessions.py`
- `apps/api/tests/test_phase4.py`
- `apps/web/app/_components/navigation.tsx`
- `apps/web/app/_components/tables.tsx`
- `apps/web/app/_components/ui.tsx`
- `apps/web/app/_lib/contracts.ts`
- `apps/web/app/_lib/format.ts`
- `apps/web/app/drivers/[driverId]/page.tsx`
- `apps/web/app/drivers/page.tsx`
- `apps/web/app/layout.tsx`
- `apps/web/app/page.tsx`
- `apps/web/app/pitwall/page.tsx`
- `apps/web/app/races/[eventId]/page.tsx`
- `apps/web/app/races/page.tsx`
- `apps/web/app/strategy/page.tsx`
- `apps/web/app/telemetry/page.tsx`
- `apps/api/app/models/core_sources.py`
- `apps/api/migrations/versions/0008_historical_core_sources.py`
- `apps/api/tests/test_v2_history.py`
- `apps/web/tests/history.test.mjs`
- `docs/superpowers/plans/2026-10-10-v2-historical-seasons.md`

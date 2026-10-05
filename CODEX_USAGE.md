# CODEX_USAGE.md

## Goal

Spend the 5-hour Codex window on implementation, not repeated reading.

## Recommended workflow

### New Codex session
Send the phase prompt from `CODEX_PROMPTS.md`.

Do not paste `AGENTS.md` or the project docs into the prompt. They already exist in the repository.

### Same session, follow-up
Use very short requests, for example:

- `Continue Phase 4 from the current state. Fix only the ingestion issue you identified.`
- `Implement the next unchecked item in Phase 6. Stay within the current telemetry files.`
- `Fix the TypeScript error in TelemetryChart only. Do not run the full build.`
- `Review your current diff for Phase 3 and fix only regressions caused by this change.`

### Avoid
Do not repeatedly say:
- the full architecture;
- the full product idea;
- the whole design brief;
- all telemetry rules;
- all prior phase results.

The repository docs already contain that context.

## Best batching

Use one Codex session for one coherent phase when possible.

Good:
- Phase 1 backend foundation
- Phase 2 ingestion
- Phase 4 telemetry ingestion
- Phase 5 comparison engine

Avoid mixing:
- frontend redesign + database migration + AI + 3D

Mixed tasks cause wider inspection and greater token use.

## When to start a new chat/session

Start fresh when:
- moving to a substantially different system;
- prior conversation has become very long;
- Codex keeps carrying irrelevant context;
- a phase is complete.

A fresh session can simply receive:

`Read AGENTS.md. Implement Roadmap Phase X only.`

## Efficient correction prompts

Instead of explaining everything again:

`The implementation is close. Fix only these issues:
1. ...
2. ...
Do not refactor unrelated code or rerun broad checks.`

## Validation

Ask for targeted validation:

`Run only the tests directly covering the telemetry comparison service.`

Instead of:

`Test everything.`

## Diff review

Useful end-of-phase prompt:

`Review only your current phase diff against AGENTS.md and the relevant project docs. Fix only issues introduced by this phase. Do not expand scope.`

This is cheaper than requesting a full repository audit after every phase.

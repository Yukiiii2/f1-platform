# Design Guidelines

## UI Rules

### Do
- Use clear hierarchy.
- Use spacing to group information.
- Use dividers before adding containers.
- Keep labels short.
- Keep telemetry values aligned.
- Use tabular numerals where possible.
- Reserve the strongest visual treatment for the current race, selected driver, or key analysis.
- Let charts and track visualizations breathe.

### Avoid
- excessive rounded cards;
- excessive pills;
- decorative gradients;
- glassmorphism;
- neon borders;
- strong shadows everywhere;
- generic dashboard tile walls;
- duplicated headings;
- fake technical labels;
- visual noise around dense telemetry.

---

## Components

Prefer reusable primitives for:
- section headers;
- metric groups;
- tabs;
- session selectors;
- driver selectors;
- lap selectors;
- telemetry legends;
- chart controls;
- stint timelines;
- status badges;
- data provenance labels.

Do not create a new component abstraction for one trivial usage.

---

## Race Status

Use clear states:
- Upcoming
- Live / In progress
- Completed
- Delayed
- Cancelled

Do not infer "Live" merely from the current clock if the backend does not confirm session status.

---

## Data Provenance Labels

Use consistent labels when needed:

- `Source data`
- `Calculated`
- `AI analysis`
- `Estimate`

Use these primarily where confusion is possible; do not clutter every number.

---

## Telemetry Charts

Every telemetry comparison should identify:
- event;
- session;
- driver;
- lap;
- tyre compound when relevant;
- tyre age when relevant;
- alignment basis.

Avoid misleading smoothing.

If interpolation is used for comparison, raw points must remain preserved in the data layer.

---

## Tyre UI

Always distinguish:
- tyre compound;
- stint laps;
- tyre age at stint start;
- laps completed in current stint;
- total estimated tyre age.

Never show "Tyre health 72%" unless a documented model produces it and the UI clearly labels it as an estimate.

---

## Loading States

Prefer:
- skeletons for content regions;
- compact loading indicators for charts;
- textual state for AI tool retrieval.

Avoid full-page loading spinners when only one panel is updating.

---

## Error States

Errors should say:
- what failed;
- whether retry is possible;
- whether data is unavailable or temporarily unreachable.

Do not replace missing telemetry with fabricated placeholder values.

---

## Empty States

Useful empty states:
- explain why data is unavailable;
- suggest another session/lap;
- distinguish "not loaded yet" from "source does not provide this."

---

## 3D Fallback

Every 3D surface must have:
- non-WebGL fallback;
- accessible textual context;
- no loss of essential data.

If 3D fails, the page still works.

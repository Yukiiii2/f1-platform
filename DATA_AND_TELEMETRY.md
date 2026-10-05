# Data and Telemetry

## Purpose

This document defines what the product may treat as source data, what it may calculate, and what must be labeled as estimation or AI interpretation.

Accuracy takes priority over visual completeness.

---

## Initial Data Sources

Potential upstream sources include:
- OpenF1;
- Jolpica;
- FastF1-backed historical processing where appropriate.

Provider availability, terms, rate limits, historical coverage, and real-time access can change. Verify current provider capabilities before implementing provider-specific features.

Do not hard-code assumptions about provider permanence.

---

## Data Classification

Every metric belongs to one of:

### 1. Source-derived
Stored from an upstream provider.

Examples:
- session result;
- lap time;
- sector times;
- driver position;
- speed;
- throttle;
- brake state;
- gear;
- RPM;
- DRS state;
- tyre compound;
- stint start/end;
- tyre age at stint start;
- pit stop;
- race-control message.

### 2. Derived
Calculated deterministically.

Examples:
- current tyre age;
- stint length;
- average stint pace;
- lap delta;
- sector delta;
- speed delta;
- position gain/loss.

Every derived metric should have:
- a documented formula;
- a version if logic may evolve;
- testable inputs/outputs.

### 3. Estimated / interpreted
Produced by heuristic/model/AI.

Examples:
- degradation estimate;
- projected pace;
- likely strategy benefit;
- likely cause of time loss.

These must be labeled.

---

## Tyre Age

When source data provides:
- `tyre_age_at_start`;
- stint start lap;
- stint end lap;

calculate current tyre age as:

```text
total_tyre_age =
tyre_age_at_start
+ completed_laps_on_current_stint
```

Be explicit about lap-boundary semantics.

For presentation, distinguish:

```text
Age when fitted: 3 laps
Current race-stint usage: 10 laps
Estimated total tyre age: 13 laps
```

Do not infer pre-stint tyre age when the upstream source does not provide it.

---

## Telemetry Storage

Keep raw telemetry immutable where practical.

Suggested logical fields:
- session_id;
- driver_id;
- lap_id where resolvable;
- timestamp;
- speed;
- throttle;
- brake;
- gear;
- rpm;
- drs;
- provider;
- provider_sample_id or source timestamp.

Provider-specific extra fields may be stored separately but should not leak into core APIs without normalization.

---

## Lap Association

Telemetry samples should be associated to:
- session;
- driver;
- timestamp;
- lap when deterministically resolvable.

If lap mapping is uncertain:
- store session/driver/time first;
- compute mapping separately;
- do not silently assign samples to the wrong lap.

---

## Comparison Alignment

Telemetry comparison may align by:
- normalized lap distance;
- elapsed lap time;
- track position if reliable enough.

Preferred for lap comparison:
1. derive/obtain lap distance;
2. resample both laps to a common distance axis;
3. retain raw samples separately;
4. compute delta traces from aligned points.

Record:
- alignment method;
- interpolation method;
- sample resolution.

Do not describe interpolated points as raw measurements.

---

## Delta

Lap delta should clearly define sign convention.

Example:

```text
delta_ms = driver_a_elapsed_ms - driver_b_elapsed_ms
```

Then document:
- positive = A is behind B;
- negative = A is ahead of B.

Keep this convention consistent across backend, charts, tooltips, and AI.

---

## Brake Channel

If the provider exposes brake only as an applied/not-applied state, the product may display:

- Brake: On
- Brake: Off

Do not convert this into fake pressure values.

---

## Unsupported Engineering Data

Unless a trusted source explicitly provides it, do not claim access to:
- tyre carcass temperature;
- tyre surface temperature;
- tyre pressure;
- brake hydraulic pressure;
- fuel mass;
- fuel flow;
- aerodynamic load;
- ride height;
- suspension forces;
- engine mode;
- differential settings;
- ERS deployment maps;
- steering torque.

---

## Strategy Analysis

Strategy analysis may use:
- stint length;
- compound;
- tyre age;
- lap pace;
- pit timing;
- gaps/intervals;
- safety car/VSC;
- weather;
- traffic indicators;
- position changes.

AI may interpret these factors, but the interpretation must not be presented as team-confirmed intent.

Use language such as:
- "likely";
- "suggests";
- "appears consistent with";
- "based on the available timing data".

Avoid:
- "the team definitely chose this because..." unless sourced.

---

## Race Replay

Replay is reconstructed.

Possible inputs:
- position samples;
- timestamps;
- intervals;
- lap timing;
- circuit geometry.

It is not an official GPS/broadcast representation unless the source explicitly provides that level of data.

Label reconstructed motion as appropriate.

---

## Data Quality

Store data-quality metadata where useful:
- provider;
- import timestamp;
- last updated;
- missing channels;
- incomplete session flag;
- validation warnings.

UI should prefer transparent "data unavailable" states over invented completeness.

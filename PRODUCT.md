# Product — F1 Intelligence Platform

## Product Vision

Build an unofficial, premium Formula 1 web platform that feels alive throughout the season.

The product combines:
- automatically updated race-weekend data;
- driver, team, circuit, and standings pages;
- qualifying and race telemetry;
- tyre stint and strategy analysis;
- interactive circuit and 3D experiences;
- an AI race engineer that explains the sport using the platform's actual data.

The site should feel less like a database and more like a digital paddock, telemetry lab, and race-engineering interface.

---

## Product Principles

1. **Data first**
   The experience must remain useful even with all animation and 3D disabled.

2. **Accuracy over spectacle**
   Never invent engineering data to make a visualization look richer.

3. **Context-aware AI**
   AI should understand the page/session/driver/lap the user is currently exploring.

4. **Season-aware**
   The site changes naturally between normal weeks, race weekends, active sessions, and post-race analysis.

5. **Premium, not cluttered**
   Dense information is allowed, but hierarchy must remain clear.

6. **Progressive complexity**
   V1 should be excellent without requiring every future live/replay feature.

---

## Primary Users

### F1 fans
Want fast, understandable answers about races, drivers, standings, strategy, and telemetry.

### Data-curious fans
Want to compare laps, sectors, tyre stints, speed traces, and strategy decisions.

### Portfolio reviewers / engineers
Should immediately see credible frontend, backend, data engineering, visualization, AI, and 3D capability.

---

## Core Navigation

- Home
- Races
- Drivers
- Teams
- Standings
- Circuits
- Telemetry Lab
- Strategy
- AI / Pitwall

Later:
- Paddock / User account
- Saved comparisons
- Predictions
- Historic seasons

---

## Homepage States

### Normal week
Show:
- next Grand Prix;
- countdown;
- championship leaders;
- latest completed race;
- featured analysis;
- driver spotlight.

### Race week
Emphasize:
- current event;
- schedule;
- session status;
- circuit;
- championship context.

### Session complete
Emphasize:
- session results;
- key telemetry;
- tyre/stint data;
- comparison suggestions.

### Race complete
Emphasize:
- podium;
- biggest movers;
- fastest lap;
- strategy timeline;
- updated standings;
- AI race report.

---

## Driver Page

Include:
- driver identity and team;
- current season position/points;
- wins, podiums, poles, fastest laps;
- form;
- race results;
- qualifying results;
- teammate comparison;
- telemetry entry points;
- tyre/stint analysis;
- career timeline;
- contextual AI.

3D is optional enhancement:
- helmet;
- car;
- curated hero scene.

---

## Race Weekend Page

Include:
- event header;
- circuit;
- local/session schedule;
- FP1 / FP2 / FP3 / Sprint / Qualifying / Race status;
- results;
- starting grid;
- lap data;
- pit stops;
- tyre strategies;
- race control;
- telemetry;
- AI recap.

---

## Telemetry Lab

Primary workflows:

### Qualifying comparison
Compare two drivers/laps:
- lap time;
- sectors;
- speed;
- throttle;
- brake state;
- gear;
- RPM;
- DRS;
- delta.

### Race lap comparison
Compare laps with tyre/stint context.

### Driver lap replay
Replay stored telemetry over a circuit visualization.

### Strategy view
Compare stint sequences, tyre age, pit timing, and pace.

---

## Tyres and Strategy

Show:
- compound;
- stint start/end;
- tyre age at stint start;
- current/ending estimated age derived from source data;
- lap counts;
- pit lap;
- average pace;
- best lap;
- traffic/safety-car context where available.

Never invent:
- tyre temperature;
- pressure;
- exact tyre-health percentage.

---

## AI — Pitwall

Pitwall is a contextual F1 intelligence assistant.

It should answer questions such as:
- Why did Driver A lose time to Driver B?
- Where was the qualifying lap gained?
- How old were the tyres at this point?
- Why did the undercut work?
- Which driver extended the first stint longest?
- How did this result affect the championship?

Pitwall should retrieve relevant data before answering.

---

## V1 Scope

V1 must include:
- homepage;
- races;
- drivers;
- standings;
- backend API;
- PostgreSQL;
- automatic post-session data ingestion;
- qualifying telemetry;
- race-lap telemetry;
- tyre stints;
- tyre age;
- lap comparison;
- Pitwall AI;
- one polished 3D experience.

Not required for V1:
- real-time timing;
- full race replay with every car;
- user accounts;
- predictions;
- historical seasons;
- predictive tyre models.

---

## Product Success

V1 is successful when a user can:

1. open a completed race weekend;
2. view trustworthy session results;
3. inspect a driver's stint and tyre age;
4. compare two qualifying or race laps;
5. see telemetry differences;
6. ask Pitwall why the difference happened;
7. receive an answer grounded in stored data;
8. navigate the experience comfortably on desktop and mobile.

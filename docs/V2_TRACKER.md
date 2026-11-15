# Nova Healix API v2: build tracker

Source of truth: the "Nova Healix API: backend guide (v2)" and the frontend repo
[hashir4825/Nova-Helix](https://github.com/hashir4825/Nova-Helix) (`src/app/core/mock/` is the reference engine).
Branch: `feature/nova-api-v2`.

Status: `[ ]` not started · `[~]` in progress · `[x]` done and tested · `[-]` deliberately dropped / deferred (reason given)

## 0. Decisions

| # | Decision | Status |
|---|---|---|
| D1 | One system: the RIDGE app (3 crew, mission days, cards) is retired; its features (ECHO, distance, dashboard, alerts, mobility) are re-expressed on the v2 core | [x] |
| D2 | Mobility & Balance Check is not in the v2 guide ("Removed"); kept as **additive** endpoints (frontend unchanged): feeds a Gravity driver and a `mobility:<crew>` finding. See docs/BACKEND_UPDATE.md section 2.1 | [x] |
| D3 | ECHO (stored, scored chat) stays for the RIDGE app; Nova is the separate private, stateless companion; nothing from Nova is stored or logged | [x] |
| D4 | JSON is camelCase on the wire (pydantic `alias_generator=to_camel`) | [x] |
| D5 | Every time is a mission hour (float since launch); never evaluate past "now" | [x] |

## 1. Endpoints (29)

| # | Method | Path | Frontend method | Status |
|---|---|---|---|---|
| 1 | GET | `/health` | ops | [x] |
| 2 | GET | `/api/mission` | `MissionApi.config` | [x] |
| 3 | GET | `/api/mission/events` | `MissionApi.events` | [x] |
| 4 | GET | `/api/crew/{id}/timeline?from&to` | `MissionApi.timeline` | [x] |
| 5 | GET | `/api/crew` | `CrewApi.list` | [x] |
| 6 | GET | `/api/crew/{id}` | convenience | [x] |
| 7 | GET | `/api/crew/{id}/metrics/{metric}?from&to&bucket` | `TelemetryApi.series` | [x] |
| 8 | GET | `/api/crew/{id}/metrics/{metric}/baseline` | `TelemetryApi.baseline` | [x] |
| 9 | GET | `/api/crew/{id}/vitals/live` | `TelemetryApi.live` | [x] |
| 10 | GET | `/api/crew/{id}/checkins?from&to` | `TelemetryApi.checkIns` | [x] |
| 11 | GET | `/api/assessment/hazards?at&autonomous` | `AssessmentApi.hazards` | [x] |
| 12 | GET | `/api/assessment/hazards/{hazard}/history?crew&fromDay&at&autonomous` | `AssessmentApi.hazardHistory` | [x] |
| 13 | GET | `/api/assessment/crew-summaries?at&autonomous` | `AssessmentApi.crewSummaries` | [x] |
| 14 | GET | `/api/insights?at&autonomous` | `AssessmentApi.insights` | [x] |
| 15 | GET | `/api/crew/{id}/metrics/{metric}/interpretation?at&autonomous` | `AssessmentApi.interpretMetric` | [x] |
| 16 | POST | `/api/crew/{id}/checkins` (201) | `CrewModeApi.submitCheckIn` | [x] |
| 17 | GET | `/api/questionnaires` | `CrewModeApi.questionnaires` | [x] |
| 18 | GET | `/api/crew/{id}/assignments` | `CrewModeApi.assignments` | [x] |
| 19 | GET | `/api/assignments/{assignmentId}` | `CrewModeApi.assignment` | [x] |
| 20 | PUT | `/api/assignments/{assignmentId}/progress` | `CrewModeApi.saveProgress` | [x] |
| 21 | POST | `/api/assignments/{assignmentId}/submit` | `CrewModeApi.submitQuestionnaire` | [x] |
| 22 | POST | `/api/crew/{id}/companion/reply` | `CompanionApi.start/send` | [x] |
| 23 | POST | `/api/crew/{id}/shared-notes` (201) | `CompanionApi.resolveCard` | [x] |
| 24 | GET | `/api/actions` | `ActionsApi.log` | [x] |
| 25 | POST | `/api/actions` (201) | `ActionsApi.record` | [x] |
| 26 | GET | `/api/crew/{id}/messages` | `ActionsApi.messages` | [x] |
| 27 | POST | `/api/crew/{id}/messages` (201) | `ActionsApi.sendMessage` | [x] |
| 28 | POST | `/api/insights/{insightId}/resolve` | `ActionsApi.resolve` | [x] |
| 29 | POST | `/api/insights/{insightId}/reopen` | `ActionsApi.reopen` | [x] |

## 1b. Additive endpoints (not in the guide)

| # | Method | Path | Status |
|---|---|---|---|
| A1 | GET | `/api/mobility/method` | [x] |
| A2 | POST | `/api/mobility/{crewId}` (201) | [x] |
| A3 | GET | `/api/mobility/{crewId}` | [x] |
| A4 | static | `/demo/mobility/` (MediaPipe test page) | [x] |
| A5 | engine | Gravity driver "Mobility & balance check" + finding `mobility:<crew>` (no checks: scores unchanged, proven by parity tests) | [x] |
| A6 | db | `mobility_sessions` table (distinct name: the RIDGE `mobility_checks` table is kept for the RIDGE app) | [x] |

## 1c. Extra features on the one core

| Item | Status |
|---|---|
| ECHO (Ahmed): `/api/isolation/*` with camelCase, crew slugs, today's mission day; feeds an Isolation driver and a `loneliness:<crew>` finding | [x] |
| Distance (Ahmed): `GET /api/distance` from the trajectory (real Horizons at the Mars end) | [x] |
| Dashboard and alerts: `GET /api/dashboard`, `GET /api/alerts` | [x] |
| One Gemini wrapper for Nova and ECHO; one companion error (503) | [x] |
| One database: 14 tables in one `supabase/schema.sql`; `cleanup_old_tables.sql` is optional | [x] |
| Duplicated RIDGE engine, models, crew generator, containers, 4 repositories removed | [x] |
| `insights.py` (1000 lines) split into a package, one module per concern; parity unchanged | [x] |

## 2. Foundation

| Item | Status |
|---|---|
| CamelCase base model (`alias_generator`, `populate_by_name`, `by_alias` responses) | [x] |
| CORS: `GET, POST, PUT, OPTIONS`; origins `http://localhost:4200` + Vercel URL | [x] |
| Mission clock: `missionHour`, `day = floor(h/24)+1`, `at` clamped to now | [x] |
| 4 crew with slug ids (`hashir`, `ahmad`, `hannan`, `sabaina`) | [x] |
| Metric catalogue (units, cadence, thresholds) ported from `core/models/metric.ts` | [x] |
| Store abstraction (in-memory + Supabase) for samples, check-ins, assignments, notes, flags, log, messages, resolutions | [x] |
| Domain errors: 404 / 409 / 422 / 503 mapping with `{"detail": ...}` | [x] |

## 3. Simulated data (ported from `generator.ts`, `personas.ts`, `mission-plan.ts`)

| Item | Status |
|---|---|
| Seeded PRNG + stats helpers | [x] |
| Mission plan (events, EVAs, SPE, burns) | [x] |
| Persona storylines per astronaut | [x] |
| Hourly vitals, daily sleep/dose, weekly/monthly metrics, environment | [x] |
| Exercise sessions (done / missed) | [x] |
| Check-in history | [x] |
| Baselines (resting hours only for vitals; 5th–95th band, min half-width) | [x] |

## 4. Assessment engine

| Item | Status |
|---|---|
| Context helpers (recent means, z-scores, `combine`) | [x] |
| Radiation hazard | [x] |
| Isolation hazard | [x] |
| Distance hazard | [x] |
| Gravity hazard | [x] |
| Environment hazard | [x] |
| Hazard history (daily) | [x] |
| Crew summaries | [x] |
| Insight rules: `sleep-debt`, `isolation-stress`, `rad-outlier`, `fluid-shift`, `exercise`, `bone-on-track`, `workload`, `co2`, `checkin`, `safety`, `note`, `q` | [x] |
| Resolution rule (resolved / reopened) and sort order | [x] |
| Metric interpretation | [x] |

## 5. Crew Mode and Nova

| Item | Status |
|---|---|
| Check-in (one per astronaut per day, replaces) + validation 1–5 | [x] |
| Questionnaires (4, verbatim from `questionnaires.ts`) + scoring + `feeds` metric | [x] |
| Assignments: progress, submit, 409 on resubmit | [x] |
| Nova: deterministic safety check before any model call | [x] |
| Nova: ambiguous hopelessness question + `pendingSafetyCheck` | [x] |
| Nova: check-in / share / breathing cards | [x] |
| Nova: Gemini fallback reply (503 on failure), `rules` fallback mode | [x] tested with a scripted stand-in; not exercised against the live Gemini API |
| Nova privacy: no storage, no logging of body/reply, bodies stripped from access logs and errors | [x] |
| Safety flag (no text) → `safety:<id>` alert insight | [x] |
| Shared notes → `note:<id>` insight | [x] |
| Action log, crew messages (signal delay from `trajectoryAu`), resolve / reopen | [x] |

## 6. NASA data

| Item | Status |
|---|---|
| DONKI events → `MissionEvent` (`spe`) + `doseRate` samples; live / cached / snapshot fallback kept | [~] events mapped onto D97 (18, `source: "NASA DONKI"`); `doseRate`/`radDose` deliberately NOT driven by them, to keep parity with the frontend demo data (see BACKEND_UPDATE.md section 1) |
| JPL Horizons → `MissionConfig.trajectoryAu` (≥ durationDays + 1 values) | [x] |

## 7. Database

| Item | Status |
|---|---|
| New `supabase/schema.sql` (tables in guide section 9, no chat table) | [~] written and cross-checked column-by-column against the repository; not yet run in a real Supabase project |
| One `supabase/schema.sql` (v2, ECHO, mobility, cache); optional `cleanup_old_tables.sql` for the earlier RIDGE tables | [x] |

## 8. Quality and docs

| Item | Status |
|---|---|
| Tests per endpoint group; checklist from guide section 10 automated | [x] |
| `make check` green (ruff, mypy strict, coverage ≥ 90%) | [x] |
| `docs/BACKEND_UPDATE.md`: the one file for the frontend team (v2 summary, every extra API, what to use); RIDGE docs kept under `docs/ridge/` | [x] |
| README / FEATURES updated | [x] |
| Compare with frontend `scripts/calibrate.ts` output at Day 142, 14:00 | [x] |
| Run frontend with `?data=api` against this server | [x] Mission Control, profile, Nova (greeting, check-in, safety), insights, action log and resolve driven in the browser; the questionnaire form was only load-checked (covered by API tests) |

## Not verified / open

- Docker image build (Docker daemon unavailable here; the container start command and health check were verified earlier).
- Supabase schema and the Supabase code path against a real project (the PostgREST calls are tested with a mocked transport).
- Live Gemini replies (rate limits, safety filters).
- Railway needs the new variables (`CORS_ORIGINS` with the frontend origin) and `supabase/schema.sql` run.

## Verification so far (against the frontend's own engine; see `scripts/frontend-golden/`)

- Seeded PRNG: bit-identical to `prng.ts`.
- Generated series: sample values, counts and last values identical for all metrics checked (`tests/fixtures/nova_golden.json`).
- 40 of 40 baselines identical; 40 of 40 hazard assessments identical (score, status, headline, explanation, every driver) at D142 14:00 and 03:00; hazard history identical.
- All insights (id, severity, title, confidence, detectedAt, summary) and metric interpretations identical at both times.

## 9. Guide checklist (section 10) → result

- [x] `GET /api/mission` returns `trajectoryAu` with at least `durationDays + 1` values
- [x] `GET /api/assessment/hazards` returns exactly 5 rows per astronaut
- [x] Unknown astronaut → 404; check-in with `mood: 9` → 422
- [x] Every GET returns the field names and types of guide section 4, camelCase
- [x] After resolve, `GET /api/insights` includes `resolution`; after reopen it is gone
- [x] Nova "I want to die" → `safety` card; `/api/insights` then starts with a `safety:…` alert with no chat text
- [x] Nothing from the Nova route is in the database, logs or error reports
- [x] Frontend `?data=api`: Mission Control, profile, check-in, Nova, resolve all work in the browser with no console errors (metric sheet and the questionnaire form were not clicked through; their endpoints are covered by tests)

## Result

`make check`: ruff and `mypy --strict` clean, 215 tests passing (parity, every endpoint, ECHO, Mobility, persistence, NASA).

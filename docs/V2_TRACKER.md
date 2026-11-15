# Nova Healix API v2: build tracker

Source of truth: the "Nova Healix API: backend guide (v2)" and the frontend repo
[hashir4825/Nova-Helix](https://github.com/hashir4825/Nova-Helix) (`src/app/core/mock/` is the reference engine).
Branch: `feature/nova-api-v2`.

Status: `[ ]` not started · `[~]` in progress · `[x]` done and tested · `[-]` deliberately dropped / deferred (reason given)

## 0. Decisions

| # | Decision | Status |
|---|---|---|
| D1 | v2 **replaces** RIDGE: old `/api/dashboard`, `/api/alerts`, `/api/distance`, `/api/isolation/*`, `/api/mobility/*` are removed | [ ] |
| D2 | Mobility & Balance Check is not in the v2 guide ("Removed"). Code stays in git history (branches merged to `development`). If it returns, results go in as `legStrength` samples | [ ] |
| D3 | ECHO Gemini chat (stored sessions, loneliness scoring) is replaced by stateless Nova; nothing from Nova is stored or logged | [ ] |
| D4 | JSON is camelCase on the wire (pydantic `alias_generator=to_camel`) | [ ] |
| D5 | Every time is a mission hour (float since launch); never evaluate past "now" | [ ] |

## 1. Endpoints (29)

| # | Method | Path | Frontend method | Status |
|---|---|---|---|---|
| 1 | GET | `/health` | ops | [ ] |
| 2 | GET | `/api/mission` | `MissionApi.config` | [ ] |
| 3 | GET | `/api/mission/events` | `MissionApi.events` | [ ] |
| 4 | GET | `/api/crew/{id}/timeline?from&to` | `MissionApi.timeline` | [ ] |
| 5 | GET | `/api/crew` | `CrewApi.list` | [ ] |
| 6 | GET | `/api/crew/{id}` | convenience | [ ] |
| 7 | GET | `/api/crew/{id}/metrics/{metric}?from&to&bucket` | `TelemetryApi.series` | [ ] |
| 8 | GET | `/api/crew/{id}/metrics/{metric}/baseline` | `TelemetryApi.baseline` | [ ] |
| 9 | GET | `/api/crew/{id}/vitals/live` | `TelemetryApi.live` | [ ] |
| 10 | GET | `/api/crew/{id}/checkins?from&to` | `TelemetryApi.checkIns` | [ ] |
| 11 | GET | `/api/assessment/hazards?at&autonomous` | `AssessmentApi.hazards` | [ ] |
| 12 | GET | `/api/assessment/hazards/{hazard}/history?crew&fromDay&at&autonomous` | `AssessmentApi.hazardHistory` | [ ] |
| 13 | GET | `/api/assessment/crew-summaries?at&autonomous` | `AssessmentApi.crewSummaries` | [ ] |
| 14 | GET | `/api/insights?at&autonomous` | `AssessmentApi.insights` | [ ] |
| 15 | GET | `/api/crew/{id}/metrics/{metric}/interpretation?at&autonomous` | `AssessmentApi.interpretMetric` | [ ] |
| 16 | POST | `/api/crew/{id}/checkins` (201) | `CrewModeApi.submitCheckIn` | [ ] |
| 17 | GET | `/api/questionnaires` | `CrewModeApi.questionnaires` | [ ] |
| 18 | GET | `/api/crew/{id}/assignments` | `CrewModeApi.assignments` | [ ] |
| 19 | GET | `/api/assignments/{assignmentId}` | `CrewModeApi.assignment` | [ ] |
| 20 | PUT | `/api/assignments/{assignmentId}/progress` | `CrewModeApi.saveProgress` | [ ] |
| 21 | POST | `/api/assignments/{assignmentId}/submit` | `CrewModeApi.submitQuestionnaire` | [ ] |
| 22 | POST | `/api/crew/{id}/companion/reply` | `CompanionApi.start/send` | [ ] |
| 23 | POST | `/api/crew/{id}/shared-notes` (201) | `CompanionApi.resolveCard` | [ ] |
| 24 | GET | `/api/actions` | `ActionsApi.log` | [ ] |
| 25 | POST | `/api/actions` (201) | `ActionsApi.record` | [ ] |
| 26 | GET | `/api/crew/{id}/messages` | `ActionsApi.messages` | [ ] |
| 27 | POST | `/api/crew/{id}/messages` (201) | `ActionsApi.sendMessage` | [ ] |
| 28 | POST | `/api/insights/{insightId}/resolve` | `ActionsApi.resolve` | [ ] |
| 29 | POST | `/api/insights/{insightId}/reopen` | `ActionsApi.reopen` | [ ] |

## 2. Foundation

| Item | Status |
|---|---|
| CamelCase base model (`alias_generator`, `populate_by_name`, `by_alias` responses) | [x] |
| CORS: `GET, POST, PUT, OPTIONS`; origins `http://localhost:4200` + Vercel URL | [ ] |
| Mission clock: `missionHour`, `day = floor(h/24)+1`, `at` clamped to now | [ ] |
| 4 crew with slug ids (`hashir`, `ahmad`, `hannan`, `sabaina`) | [x] |
| Metric catalogue (units, cadence, thresholds) ported from `core/models/metric.ts` | [x] |
| Store abstraction (in-memory + Supabase) for samples, check-ins, assignments, notes, flags, log, messages, resolutions | [ ] |
| Domain errors: 404 / 409 / 422 / 503 mapping with `{"detail": ...}` | [ ] |

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
| Crew summaries | [ ] |
| Insight rules: `sleep-debt`, `isolation-stress`, `rad-outlier`, `fluid-shift`, `exercise`, `bone-on-track`, `workload`, `co2`, `checkin`, `safety`, `note`, `q` | [x] |
| Resolution rule (resolved / reopened) and sort order | [x] |
| Metric interpretation | [x] |

## 5. Crew Mode and Nova

| Item | Status |
|---|---|
| Check-in (one per astronaut per day, replaces) + validation 1–5 | [ ] |
| Questionnaires (4, verbatim from `questionnaires.ts`) + scoring + `feeds` metric | [~] data + scoring done; endpoints pending |
| Assignments: progress, submit, 409 on resubmit | [ ] |
| Nova: deterministic safety check before any model call | [ ] |
| Nova: ambiguous hopelessness question + `pendingSafetyCheck` | [ ] |
| Nova: check-in / share / breathing cards | [ ] |
| Nova: Gemini fallback reply (503 on failure), `rules` fallback mode | [ ] |
| Nova privacy: no storage, no logging of body/reply, bodies stripped from access logs and errors | [ ] |
| Safety flag (no text) → `safety:<id>` alert insight | [ ] |
| Shared notes → `note:<id>` insight | [ ] |
| Action log, crew messages (signal delay from `trajectoryAu`), resolve / reopen | [ ] |

## 6. NASA data

| Item | Status |
|---|---|
| DONKI events → `MissionEvent` (`spe`) + `doseRate` samples; live / cached / snapshot fallback kept | [ ] |
| JPL Horizons → `MissionConfig.trajectoryAu` (≥ durationDays + 1 values) | [ ] |

## 7. Database

| Item | Status |
|---|---|
| New `supabase/schema.sql` (tables in guide section 9, no chat table) | [ ] |
| Drop RIDGE tables (`isolation_chat_*`, `loneliness_assessments`, `mobility_checks`, `daily_records`) in a migration note | [ ] |

## 8. Quality and docs

| Item | Status |
|---|---|
| Tests per endpoint group; checklist from guide section 10 automated | [ ] |
| `make check` green (ruff, mypy strict, coverage ≥ 90%) | [ ] |
| `docs/API_V2.md` (the guide) replaces `FRONTEND_API_GUIDE.md` | [ ] |
| README / FEATURES updated | [ ] |
| Compare with frontend `scripts/calibrate.ts` output at Day 142, 14:00 | [ ] |
| Run frontend with `?data=api` against this server | [ ] |

## Verification so far (against the frontend's own engine, `npx tsx scripts/dump-golden.ts`)

- Seeded PRNG: bit-identical to `prng.ts`.
- Generated series: sample values, counts and last values identical for all metrics checked (`tests/fixtures/nova_golden.json`).
- 40 of 40 baselines identical; 40 of 40 hazard assessments identical (score, status, headline, explanation, every driver) at D142 14:00 and 03:00; hazard history identical.
- All insights (id, severity, title, confidence, detectedAt, summary) and metric interpretations identical at both times.

## 9. Guide checklist (section 10) → result

- [ ] `GET /api/mission` returns `trajectoryAu` with at least `durationDays + 1` values
- [ ] `GET /api/assessment/hazards` returns exactly 5 rows per astronaut
- [ ] Unknown astronaut → 404; check-in with `mood: 9` → 422
- [ ] Every GET returns the field names and types of guide section 4, camelCase
- [ ] After resolve, `GET /api/insights` includes `resolution`; after reopen it is gone
- [ ] Nova "I want to die" → `safety` card; `/api/insights` then starts with a `safety:…` alert with no chat text
- [ ] Nothing from the Nova route is in the database, logs or error reports
- [ ] Frontend `?data=api`: Mission Control, profile, metric sheet, check-in, questionnaire, Nova, resolve all work

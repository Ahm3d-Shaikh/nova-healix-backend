# Nova Healix API v2: how this backend implements the guide

The contract (every endpoint, type and rule) is the **Nova Healix API v2 guide** shipped with the frontend:
[hashir4825/Nova-Helix](https://github.com/hashir4825/Nova-Helix) → `docs/BACKEND_API_GUIDE.md`. The frontend's
in-browser mock (`src/app/core/mock/`) is the reference for every rule. This page says what the backend does
about it, what is verified, and where it differs on purpose.

> **Decision support prototype, not a medical device.** Crew data is simulated. Space weather (NASA DONKI) and
> distance (NASA JPL Horizons) can be real NASA data.

Progress and per-item status: [V2_TRACKER.md](V2_TRACKER.md). Live docs: `/docs` (Swagger).

## 1. What is implemented

All 29 endpoints of the guide, camelCase JSON, times in mission hours:

| Area | Endpoints |
|---|---|
| Ops | `GET /health` → `{status, companion: "gemini"\|"rules"\|"off", missionHour}` |
| Mission | `GET /api/mission`, `GET /api/mission/events`, `GET /api/crew/{id}/timeline?from&to` |
| Crew | `GET /api/crew`, `GET /api/crew/{id}` |
| Telemetry | `GET /api/crew/{id}/metrics/{metric}?from&to&bucket`, `…/baseline`, `GET /api/crew/{id}/vitals/live`, `GET /api/crew/{id}/checkins?from&to` |
| Assessment | `GET /api/assessment/hazards`, `…/hazards/{hazard}/history?crew&fromDay`, `…/crew-summaries`, `GET /api/insights`, `GET /api/crew/{id}/metrics/{metric}/interpretation` (all take `at`, `autonomous`) |
| Crew Mode | `POST /api/crew/{id}/checkins`, `GET /api/questionnaires`, `GET /api/crew/{id}/assignments`, `GET /api/assignments/{id}`, `PUT …/progress`, `POST …/submit` |
| Nova | `POST /api/crew/{id}/companion/reply`, `POST /api/crew/{id}/shared-notes` |
| Actions | `GET/POST /api/actions`, `GET/POST /api/crew/{id}/messages`, `POST /api/insights/{id}/resolve`, `POST /api/insights/{id}/reopen` |

The RIDGE endpoints (`/api/dashboard`, `/api/alerts`, `/api/distance`, `/api/isolation/*`, `/api/mobility/*`) are gone.

## 2. Verified against the frontend

- **Parity** (`tests/test_parity.py`): the Python engine reproduces the frontend's own engine exactly: the seeded
  random generator is bit-identical; generated series, 40 baselines, all 20 hazard assessments (score, status,
  headline, explanation, every driver), hazard history, every insight (id, severity, title, confidence, summary) and
  every metric interpretation match at D142 14:00 and 03:00; Nova's replies and cards match for 19 inputs.
  Fixtures are exported by `scripts/frontend-golden/` (see its README to regenerate).
- **The real frontend** was run against this server (`?data=api`): Mission Control, a crew profile, Nova (greeting,
  check-in, safety), Crew Mode, insights, logging an action and resolving a finding all work with no console errors,
  and every call returned 2xx.
- The guide's checklist (section 10) is automated in `tests/test_v2_api.py`.

## 3. How it is built

```
app/
├── domain/        # pure logic, no I/O: prng, stats, generator, store, engine/{hazards,insights,interpret}, nova
├── schemas/       # pydantic models = the frontend's TypeScript types (camelCase on the wire)
├── services/      # clock, telemetry, analysis (cached per quarter hour), crew_mode, companion, actions, nasa
├── repositories/  # state.py (write-through persistence), cache.py (external feeds)
├── db/            # Supabase (PostgREST over httpx) and in-memory backends
├── routers/       # thin HTTP layer
└── data/          # metrics/personas/events/questionnaires exported from the frontend; DONKI snapshot
```

- **Time**: every time is a mission hour. The launch epoch is stored in the `mission` table on first start (so saved
  hours stay valid across restarts) and re-anchored to day 142 only if "now" leaves the generated data window.
  `at` is clamped to now.
- **Simulation**: the crew is generated deterministically in memory (about 0.5 s at start, 4 crew × 146 days) and is
  not stored. Only runtime writes are persisted.
- **Persistence**: services write to the database first, then update memory, so a failed write never leaves memory
  ahead. At start memory is rebuilt from the database; if the database is down the simulation still serves and writes
  return 503.
- **Findings**: ids are stable; `GET /api/insights` merges resolutions (resolved, or `reopened: true` when the finding
  got more severe since).

## 4. Nova privacy contract (as implemented)

1. `POST …/companion/reply` is stateless. The message, history and reply are never stored or logged (the access
   log records method, path and status only; 422 responses never echo the submitted text). Tests check the database
   contents and that no chat table exists.
2. Conversation never reaches the analysis engine or Mission Control. There is no loneliness scoring.
3. Only confirmed shares leave the chat: a check-in (`POST …/checkins`, no note) or a note (`POST …/shared-notes`).
4. **Safety exception**: a deterministic check runs on every message *before* anything else, and before any model call.
   Self-harm or an acute medical red flag returns a pre-written reply with a `safety` card and records a flag with
   a category and a signal only (the `safety_flags` table has no text column). Ambiguous hopelessness asks directly
   first (`pendingSafetyCheck`); a "yes" raises `confirmed-when-asked`. The flag is held in memory first, so the alert
   is never lost even if the database is down. It appears first in `GET /api/insights` as `safety:<id>`.
5. Gemini (optional, `GEMINI_API_KEY`) writes only open-ended replies, sees the astronaut's first name and the
   conversation, never wearable data, and any failure returns 503. Without a key Nova answers from its rules.

## 5. NASA data

- **DONKI**: the real May 2024 storm (live → cached → bundled snapshot) is replayed on mission day 97: the first
  real particle event lines up with the mission's own solar particle event (`spe-97`). 18 events (every SEP, X-class
  flares, Kp 7+ storms) are added to `GET /api/mission/events` with `source: "NASA DONKI"`.
  *Deviation from the guide*: the events do **not** change `doseRate` / `radDose`. Doing so would make the numbers
  differ from the frontend's demo data (and break parity); the day-97 dose spike is already part of the simulation.
- **JPL Horizons**: the real Earth-Mars distance on the arrival date (launch + 260 d) sets the far end of
  `trajectoryAu` (`trajectorySource: "NASA JPL Horizons"`); the curve keeps the frontend's shape. Cached in
  `external_data_cache`; on failure the frontend's model curve is used. The signal delay everywhere derives from it.
- Both refresh in the background at start. The API never waits on NASA.

## 6. Differences from the guide (deliberate)

| Guide | Here | Why |
|---|---|---|
| `mission`, `trajectory`, `astronauts`, `mission_events`, `samples`, `exercise_sessions`, `baselines` tables | not created; `mission` holds only the launch epoch; `samples` holds only runtime-added samples | the simulation is deterministic and generated in memory; storing 175k rows would add nothing |
| DONKI events raise `doseRate` | events are added, dose unchanged | see section 5 |
| Example check-in draft in 5.7 shows `energy: 3` | returns `energy: 2` for that text | the frontend's own engine returns 2; the example is illustrative |
| 422 body | `{"detail": "<message>"}` string (field: message) | matches section 11 and never echoes input |
| Questionnaire answers | scale answers must be 1-5 (else 422); unknown question id → 422 | not specified |
| Mobility & Balance Check | removed with the RIDGE API | the guide marks it "Removed". It remains in git history; if it returns, write results as `legStrength` samples |

## 7. Run, deploy

```bash
make install && cp .env.example .env
make run                    # http://127.0.0.1:8000/docs
make check                  # ruff, mypy --strict, pytest (coverage >= 90 %)
```

Frontend against it: in the frontend repo run `npm start` and open `http://localhost:4200/?data=api`.

Railway: set `NASA_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, optionally `GEMINI_API_KEY`, and
`CORS_ORIGINS` (add the deployed frontend origin). Run `supabase/schema.sql` once; run
`supabase/drop_ridge_tables.sql` once to remove the old RIDGE tables (it deletes old chat transcripts).
Memory use is about 80-100 MB; no ML model runs on the server.

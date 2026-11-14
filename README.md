# RIDGE Monitor — Backend (Nova Healix)

FastAPI backend for **RIDGE Monitor**, a crew health dashboard built on NASA's five
spaceflight hazards (**R**adiation, **I**solation, **D**istance, **G**ravity, **E**nvironment)
plus **Mirror Gap**, which checks whether an astronaut's self-assessment can be trusted.
Built for NASA Space Apps 2026 — *Create Health Monitoring Software for Astronauts on Space Missions*.

> **Decision support prototype, not a medical device. Crew data is simulated; space-weather data is real NASA data.**

- **Live API docs (Swagger):** https://nova-healix-backend-production.up.railway.app/docs
- Full product/context brief: [docs/RIDGE_CONTEXT.md](docs/RIDGE_CONTEXT.md)
- Frontend API guide (requests, responses, chatbot integration): [docs/FRONTEND_API_GUIDE.md](docs/FRONTEND_API_GUIDE.md)
- Earlier planning docs (written before the Supabase / Horizons / Gemini changes, partly outdated):
  [docs/FEATURES.md](docs/FEATURES.md), [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md), [docs/COVERAGE.md](docs/COVERAGE.md)

## Project structure

```text
app/
├── main.py              # create_app() factory, CORS/gzip/request-context middleware, error mapping
├── container.py         # builds and wires all services (dependency injection root)
├── core/                # config (env), mission timeline, domain errors, logging, middleware
├── models/              # Pydantic schemas (enums, alert, crew, typed card metrics, ...)
├── rules/               # pure rules engine; thresholds.py = single source of truth for every limit
├── db/                  # table gateway: Supabase (PostgREST over httpx) + in-memory backend
├── repositories/        # typed persistence per aggregate (crew, settings, mirror gap, isolation, cache)
├── services/            # DONKI + JPL Horizons clients with fallbacks, crew generator, Gemini check-in
│                        #   companion, crew / isolation / settings services
├── routers/             # thin HTTP endpoints, typed return models
├── api/deps.py          # FastAPI dependencies
└── data/                # real DONKI + Horizons responses used as offline fallbacks
supabase/schema.sql      # tables to create in the Supabase project
scripts/                 # build_snapshot.py, build_horizons_snapshot.py, check_donki_live.py
tests/                   # pytest suite (offline; real DONKI payload replays)
```

Design rules: rules are pure functions of a `RuleContext` (no I/O); every threshold lives in
`app/rules/thresholds.py` tagged `[NASA]` / `[CSA]` / `[PAPER]` / `[OURS]`; routers contain no
business logic and no error handling (domain errors are mapped to HTTP in one place); the DONKI
client and clocks are injected, so tests need no network and no sleeping.

## Endpoints

Full request/response reference and the chatbot integration guide for the frontend:
[docs/FRONTEND_API_GUIDE.md](docs/FRONTEND_API_GUIDE.md).

| Method | Path | Returns |
|---|---|---|
| GET | `/api/crew?day=N` | Astronauts with overall + per-card status |
| GET | `/api/crew/{id}?day=N` | Records up to day N, six cards (R/I/D/G/E/MIRROR), alerts, gap series |
| GET | `/api/alerts?day=N` | All amber/red alerts across the crew, worst first |
| GET | `/api/dashboard?day=N` | **One call for the dashboard**: settings, data-source status, 6 cards per astronaut (level + numeric `metrics` + rule results), alert panel |
| GET | `/api/distance` | Earth distance + one-way light time per mission day (JPL Horizons) |
| GET | `/api/isolation/method` | How AI check-ins are scored: instrument, items, thresholds, turn limits |
| POST | `/api/isolation/{id}/sessions?day=` | Start an AI check-in chat → session + companion's opening message |
| POST | `/api/isolation/{id}/sessions/{sid}/messages` | Body `{content}` → companion reply, `can_complete`, `must_complete` |
| POST | `/api/isolation/{id}/sessions/{sid}/complete` | Score the chat → loneliness score 3-9, confidence, level, alert (idempotent) |
| GET | `/api/isolation/{id}/sessions/{sid}` | Transcript + assessment |
| GET | `/api/isolation/{id}` | Loneliness score history (simulated + AI check-ins) |
| GET | `/health` | Liveness check + `database` backend + whether AI check-ins are enabled |

Every rule result is `{rule, hazard, level, what, why, action, source}`. Card `metrics` are typed and
discriminated by `kind` (see `/openapi.json`). `day` must be 1-30 (otherwise HTTP 422); POST check-ins accept
an optional `?day=` and default to the saved current day (stored in the `mission_settings` table in Supabase,
which also holds the mission and deep-space mode). Errors are `{"detail": "..."}`.
Every response carries `X-Request-ID` and `X-Process-Time-Ms`.

## Data: real vs simulated

- **Real:** NASA DONKI space weather (SEP, flares, CME, storms, notifications); JPL Horizons geocentric
  ephemeris for the ISS / Moon / Mars (distance, one-way light time); limits from NASA-STD-3001
  briefs; neutron figures from CSA Radi-N2; Three-Item Loneliness Scale; PVT-B test design.
- **Simulated (seeded):** crew vitals, sleep, exercise, CO2/temperature, baseline loneliness, daily dose.
  On first start the simulated crew is written to the database; afterwards it is read from there.
- One real DONKI solar episode (8–12 May 2024) is inserted into the mission timeline on day 20.
- All thresholds we invented are marked *illustrative*. The app "flags readings for review"; it does not diagnose.
- DONKI resilience: live (cached 1 h) → last cached copy → bundled snapshot. When `/DONKI/FLR` is unavailable,
  flares are derived from DONKI notifications. A failing API is not retried for 60 s.

## Getting started

```bash
make install                       # venv + dev dependencies
cp .env.example .env               # set NASA_API_KEY (free at https://api.nasa.gov)
make run                           # uvicorn with reload
```

- API: http://127.0.0.1:8000 · Swagger: http://127.0.0.1:8000/docs · ReDoc: http://127.0.0.1:8000/redoc

### Quality gate

```bash
make check      # ruff lint + format check, mypy --strict, pytest with coverage >= 90 % (what CI runs)
make format     # auto-fix lint + formatting
```

CI (`.github/workflows/ci.yml`) runs the same gate and a Docker build. Optional: `pre-commit install`.

### Verify live NASA DONKI access

`DEMO_KEY` allows only ~10 calls/hour, so use your own free key from https://api.nasa.gov
(one live refresh = 5 calls, cached for 1 h):

```bash
NASA_API_KEY=your_key python -m scripts.check_donki_live   # per-feed report + snapshot comparison
NASA_API_KEY=your_key pytest -m live                        # opt-in live test
```

The regular test suite replays real saved DONKI responses (`tests/fixtures/donki`), including
429 rate limits, 5xx retries and network errors. `/api/dashboard` reports `space_weather.reason: rate_limited`
when NASA throttles the key, and the app keeps serving cache/snapshot data.

### Refresh the DONKI snapshot

Save `SEP.json`, `CME.json`, `GST.json`, `notifications.json` (and optionally `FLR.json`) from
`https://api.nasa.gov/DONKI/<feed>?startDate=…&endDate=…&api_key=…` into a folder, then:

```bash
python -m scripts.build_snapshot path/to/raw
```

## Deployment

`Dockerfile`: slim Python 3.12, non-root user, installs the fully pinned `requirements.lock`, health check on
`/health`, honours `$PORT` (Railway). Set `NASA_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` and
`GEMINI_API_KEY` in the service variables.
`requirements.txt` lists direct dependencies; regenerate the lock after changing them
(`pip install -r requirements.txt && pip freeze > requirements.lock` in a clean venv).

## Isolation: AI check-in companion

Instead of a form, astronauts chat with **ECHO**, a Google Gemini-powered companion (`GEMINI_MODEL`, default
`gemini-3.8-flash`, available on the free tier). ECHO naturally covers the three Three-Item Loneliness Scale themes (companionship,
feeling left out, feeling isolated). After 3-10 replies the client calls `/complete`, and a **separate rater
call** reads the transcript and returns, as structured output, a 1-3 rating per item with quoted evidence,
a confidence (0-1) and a safety flag (Gemini structured output, validated server-side). The backend then scores deterministically:

| Step | Rule | Provenance |
|---|---|---|
| Score | q1 + q2 + q3 → 3-9 | Hughes et al. 2004 |
| Green | 3-5 | Hughes et al. 2004 |
| Amber | ≥ 6 | Hughes et al. 2004 |
| Red | ≥ 7 on 3 consecutive days, **or** a safety concern (hopelessness, self-harm, not coping) | ours, illustrative |
| Unreliable | confidence < 0.6 → stored, capped at amber, never drives the card | ours |

Reliable check-ins replace that day's simulated score on the Isolation card and alerts.
All limits live in `app/rules/thresholds.py`. Gemini safety filters are set to block only high-risk content so
astronauts can talk about distress; if a reply is still blocked, ECHO sends a fixed supportive message pointing
to the flight surgeon. **Free-tier note:** Google may use free-tier prompts and responses to improve its products,
and free quotas are small and can change; use a paid key for real crew data.

## Database (Supabase)

Run [`supabase/schema.sql`](supabase/schema.sql) once in the Supabase SQL editor, then set
`SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`. Row Level Security is **off** on all tables, so keep the
project's anon key private (never ship it in the frontend). Without them the app uses an in-memory store (tests, quick demos).
If Supabase is unreachable at startup the dashboard still serves the simulated crew; reads/writes that need the
database return HTTP 503.

## Sources

NASA [Human Body in Space (RIDGE)](https://www.nasa.gov/humans-in-space/the-human-body-in-space/) ·
[DONKI API](https://ccmc.gsfc.nasa.gov/DONKI/api/) ·
[Radiation protection brief](https://www.nasa.gov/wp-content/uploads/2023/03/radiation-protection-technical-brief-ochmo.pdf) ·
CO₂ briefs ([1](https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-004-carbon-dioxide.pdf), [2](https://nasa.gov/wp-content/uploads/2023/03/co2-technical-brief-ochmo.pdf)) ·
[ECLSS brief](https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-002-eclss.pdf) ·
[CSA Radi-N2](https://www.asc-csa.gc.ca/eng/sciences/radi-n2.asp) ·
[CSA Bio-Monitor](https://hdiac.dtic.mil/articles/peak-performance-in-microgravity) ·
[Three-Item Loneliness Scale](https://www.phenxtoolkit.org/toolkit_content/supplemental_info/psychosocial/measures/Social_Isolation.doc) ·
[PVT-B validation](https://pmc.ncbi.nlm.nih.gov/articles/PMC3197786) ·
[3-min PVT lapse bands](https://pmc.ncbi.nlm.nih.gov/articles/PMC3190077) ·
[Subjective vs objective gap](https://www.24-7pressrelease.com/press-release/414258/clearing-the-space-fog) ·
[AURORA](https://github.com/fabriciojunio/aurora-astronaut-health) ·
[JPL Horizons API](https://ssd-api.jpl.nasa.gov/doc/horizons.html) ·
[Gemini API](https://ai.google.dev/gemini-api/docs).

## Known limitations (deliberate for the hackathon)

- Settings (mission, day, deep-space mode) are one deployment-wide demo state, not per user.
- No authentication or rate limiting on the API; CORS is restricted to configured origins. Add auth before
  exposing check-in transcripts to anyone but the crew member and flight surgeon.
- The crew's location is modelled by the mission destination (ISS / Moon / Mars), not a spacecraft trajectory.
- Routes live under `/api` (no version prefix) to match the agreed frontend contract.

## Use of AI

Parts of this backend were written with AI assistance (Claude Code) and reviewed by the team.

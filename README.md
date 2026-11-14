# RIDGE Monitor — Backend (Nova Healix)

FastAPI backend for **RIDGE Monitor**, a crew health dashboard built on NASA's five
spaceflight hazards (**R**adiation, **I**solation, **D**istance, **G**ravity, **E**nvironment)
plus **Mirror Gap**, which checks whether an astronaut's self-assessment can be trusted.
Built for NASA Space Apps 2026 — *Create Health Monitoring Software for Astronauts on Space Missions*.

> **Decision support prototype, not a medical device. Crew data is simulated; space-weather data is real NASA data.**

- **Live API docs (Swagger):** https://nova-healix-backend-production.up.railway.app/docs
- Full product/context brief: [docs/RIDGE_CONTEXT.md](docs/RIDGE_CONTEXT.md)
- What has been built so far: [docs/FEATURES.md](docs/FEATURES.md)
- Requirements and backend coverage: [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md), [docs/COVERAGE.md](docs/COVERAGE.md)

## Project structure

```text
app/
├── main.py              # create_app() factory, CORS/gzip/request-context middleware, error mapping
├── container.py         # builds and wires all services (dependency injection root)
├── core/                # config (env), mission timeline, domain errors, logging, middleware
├── models/              # Pydantic schemas (enums, alert, crew, typed card metrics, ...)
├── rules/               # pure rules engine; thresholds.py = single source of truth for every limit
├── services/            # DONKI client + parsers, space-weather fallback, crew generator,
│                        #   crew / mirror-gap / isolation / settings services, in-memory store
├── routers/             # thin HTTP endpoints, typed return models
├── api/deps.py          # FastAPI dependencies
└── data/donki_snapshot.json   # real DONKI response used as offline fallback
scripts/                 # build_snapshot.py, check_donki_live.py
tests/                   # pytest suite (offline; real DONKI payload replays)
```

Design rules: rules are pure functions of a `RuleContext` (no I/O); every threshold lives in
`app/rules/thresholds.py` tagged `[NASA]` / `[CSA]` / `[PAPER]` / `[OURS]`; routers contain no
business logic and no error handling (domain errors are mapped to HTTP in one place); the DONKI
client and clocks are injected, so tests need no network and no sleeping.

## Endpoints

| Method | Path | Returns |
|---|---|---|
| GET | `/api/space-weather?deep_space_mode=` | Normalized DONKI events + `source: live \| cached \| snapshot` |
| GET | `/api/crew?day=N` | Astronauts with overall + per-card status |
| GET | `/api/crew/{id}?day=N` | Records up to day N, six cards (R/I/D/G/E/MIRROR), alerts, gap series |
| GET | `/api/alerts?day=N` | All amber/red alerts across the crew, worst first |
| POST | `/api/mirror-gap/{id}` | Body `{self_rating, reaction_times_ms[], mode}` → lapses, false starts, gap, level |
| GET | `/api/mirror-gap/{id}` | Mirror Gap history (simulated + submitted) |
| GET / POST | `/api/settings` | Mission (iss/moon/mars), deep space mode, current mission day |
| GET | `/api/dashboard?day=N` | **One call for the dashboard**: settings, data-source status, 6 cards per astronaut (level + numeric `metrics` + rule results), alert panel |
| GET | `/api/timeline?astronaut=` | Card levels for all 30 days (day slider, history charts) + real storm days |
| GET | `/api/isolation/questionnaire` | Three-Item Loneliness Scale questions/options/bands |
| POST | `/api/isolation/{id}` | Body `{q1,q2,q3}` (1-3) → score, level, consecutive-days-≥7 |
| GET | `/api/isolation/{id}` | Loneliness score history (simulated + submitted) |
| GET | `/api/meta` | Disclaimer, real-vs-simulated data table, every threshold with provenance, all sources |
| POST | `/api/demo/reset` | Back to day 5 / Mars / live; clears submitted check-ins (repeatable demo) |
| GET | `/health` | Liveness check |

Every rule result is `{rule, hazard, level, what, why, action, source}`. Card `metrics` are typed and
discriminated by `kind` (see `/openapi.json`). `day` must be 1-30 (otherwise HTTP 422); POST check-ins accept
an optional `?day=` and default to the saved current day. Errors are `{"detail": "..."}`.
Every response carries `X-Request-ID` and `X-Process-Time-Ms`.

## Data: real vs simulated

- **Real:** NASA DONKI space weather (SEP, flares, CME, storms, notifications); limits from NASA-STD-3001
  briefs; neutron figures from CSA Radi-N2; Three-Item Loneliness Scale; PVT-B test design.
- **Simulated (seeded):** crew vitals, sleep, exercise, CO2/temperature, questionnaire answers, daily dose.
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
429 rate limits, 5xx retries and network errors. `/api/space-weather` reports `reason: rate_limited`
when NASA throttles the key, and the app keeps serving cache/snapshot data.

### Refresh the DONKI snapshot

Save `SEP.json`, `CME.json`, `GST.json`, `notifications.json` (and optionally `FLR.json`) from
`https://api.nasa.gov/DONKI/<feed>?startDate=…&endDate=…&api_key=…` into a folder, then:

```bash
python -m scripts.build_snapshot path/to/raw
```

## Deployment

`Dockerfile`: slim Python 3.12, non-root user, installs the fully pinned `requirements.lock`, health check on
`/health`, honours `$PORT` (Railway). Set `NASA_API_KEY` in the service variables.
`requirements.txt` lists direct dependencies; regenerate the lock after changing them
(`pip install -r requirements.txt && pip freeze > requirements.lock` in a clean venv).

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
[AURORA](https://github.com/fabriciojunio/aurora-astronaut-health). The same list is served at `GET /api/meta`.

## Known limitations (deliberate for the hackathon)

- Settings (mission, day, deep-space mode) are one process-wide demo state, not per user.
- Mirror Gap / isolation submissions are saved to JSON files in `SUBMISSIONS_DIR` (default `var/`); on
  Railway mount a volume there or they reset on redeploy. Run a single worker.
- No authentication or rate limiting on the API; CORS is restricted to configured origins.
- Routes live under `/api` (no version prefix) to match the agreed frontend contract.

## Use of AI

Parts of this backend were written with AI assistance (Claude Code) and reviewed by the team.

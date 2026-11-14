# RIDGE Monitor — Backend (Nova Healix)

FastAPI backend for **RIDGE Monitor**, a crew health dashboard built on NASA's five
spaceflight hazards (**R**adiation, **I**solation, **D**istance, **G**ravity, **E**nvironment)
plus **Mirror Gap**, which checks whether an astronaut's self-assessment can be trusted.
Built for NASA Space Apps 2026 — *Create Health Monitoring Software for Astronauts on Space Missions*.

> **Decision support prototype, not a medical device. Crew data is simulated; space-weather data is real NASA data.**

- **Live API docs (Swagger):** https://nova-healix-backend-production.up.railway.app/docs
- Full product/context brief: [docs/RIDGE_CONTEXT.md](docs/RIDGE_CONTEXT.md)

## Project structure

```text
app/
├── main.py              # create_app() factory, CORS, router wiring
├── container.py         # builds and wires all services
├── core/                # config (env settings), mission timeline
├── models/              # Pydantic schemas (enums, alert, crew, space weather, mirror gap, settings)
├── rules/               # pure rules engine: radiation, isolation, distance, gravity,
│                        #   environment, mirror_gap, engine (worst-of per card)
├── services/            # DONKI client + parsers, space-weather fallback, crew generator,
│                        #   crew / mirror-gap / settings services
├── routers/             # HTTP endpoints
├── api/deps.py          # FastAPI dependencies
└── data/donki_snapshot.json   # real DONKI response used as offline fallback
scripts/build_snapshot.py      # regenerate the snapshot from raw DONKI JSON
tests/                         # pytest suite (no network needed)
```

Design rules: rules are pure functions of a `RuleContext`, so logic lives in one place and is
unit-testable; routers are thin; the DONKI client is injected, so tests run offline.

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
| GET | `/health` | Liveness check |

Every rule result is `{rule, hazard, level, what, why, action, source}`.

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
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # set NASA_API_KEY (free at https://api.nasa.gov)
uvicorn app.main:app --reload
```

- API: http://127.0.0.1:8000 · Swagger: http://127.0.0.1:8000/docs · ReDoc: http://127.0.0.1:8000/redoc

### Tests

```bash
pip install -r requirements-dev.txt
pytest
```

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

A `Dockerfile` is included (Railway-compatible, honours `$PORT`).

## Use of AI

Parts of this backend were written with AI assistance (Claude Code) and reviewed by the team.

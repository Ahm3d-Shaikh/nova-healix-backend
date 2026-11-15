# Nova Healix: backend

FastAPI backend for **Nova Healix**, a crew health monitor for a 4-person Mars transit, organised around NASA's
five hazards of human spaceflight (**R**adiation, **I**solation, **D**istance, **G**ravity, **E**nvironment).
Built for NASA Space Apps 2026 — *Create Health Monitoring Software for Astronauts on Space Missions*.

> **Decision support prototype, not a medical device. Crew data is simulated. Space weather (NASA DONKI) and
> distance (NASA JPL Horizons) can be real NASA data.**

- **Live API docs (Swagger):** https://nova-healix-backend-production.up.railway.app/docs
- **How it works, what is verified, deliberate differences:** [docs/API_V2.md](docs/API_V2.md)
- **Build tracker (every endpoint and rule, with status):** [docs/V2_TRACKER.md](docs/V2_TRACKER.md)
- **Contract (types, endpoints, rules):** the v2 guide in the frontend repo
  [hashir4825/Nova-Helix](https://github.com/hashir4825/Nova-Helix) → `docs/BACKEND_API_GUIDE.md`
- Earlier RIDGE brief (historical): [docs/archive/RIDGE_CONTEXT.md](docs/archive/RIDGE_CONTEXT.md)

## What it does

- **Analysis engine** ("the AI"): per-astronaut personal baselines (their own data, never a population average), a
  0-100 score for each of the 5 hazards with weighted drivers and a plain-language explanation, findings with
  evidence and recommended actions, and a reading of any single metric. A line-for-line port of the frontend's engine,
  checked against it by tests.
- **Simulated crew** (seeded, deterministic): 4 astronauts, 146 days of hourly vitals, sleep, dose, CO₂, bone and
  muscle, labs, check-ins, with planted storylines (sleep debt before an EVA, isolation stress, fluid shift, dose outlier).
- **Crew Mode**: daily check-ins and questionnaires shared with Mission Control.
- **Nova**: the astronaut's private companion. Nothing from the chat is stored, logged or analysed; the only things
  that leave it are what the astronaut confirms, plus a content-free safety alert under the safety exception.
- **Mission Control**: findings, action log, messages that carry the real signal delay, resolve / reopen.
- **Real NASA data**: DONKI storm events on mission day 97; JPL Horizons Earth-Mars distance for the trajectory.

## Getting started

```bash
make install                       # venv + dev dependencies
cp .env.example .env               # NASA_API_KEY is free at https://api.nasa.gov
make run                           # http://127.0.0.1:8000/docs
```

Frontend against it: in [Nova-Helix](https://github.com/hashir4825/Nova-Helix) run `npm start` and open
`http://localhost:4200/?data=api`.

```bash
make check      # ruff, mypy --strict, pytest with coverage >= 90 % (what CI runs)
make format     # auto-fix lint + formatting
NASA_API_KEY=your_key python -m scripts.check_donki_live   # verify live NASA access
```

## Project structure

```text
app/
├── main.py          # create_app() factory, CORS (GET/POST/PUT), middleware, error mapping
├── container.py     # wires the services
├── domain/          # pure logic: generator, store, scoring engine, Nova rules
├── schemas/         # pydantic models = the frontend's types (camelCase)
├── services/        # clock, telemetry, analysis, crew mode, companion, actions, NASA feeds
├── repositories/    # write-through persistence; external-feed cache
├── db/              # Supabase (PostgREST) and in-memory backends
├── routers/         # thin HTTP endpoints
└── data/            # data exported from the frontend; real DONKI snapshot
supabase/            # schema.sql (run once), drop_ridge_tables.sql (one-off cleanup)
scripts/             # check_donki_live, build_snapshot, frontend-golden (regenerate parity fixtures)
tests/               # pytest: parity with the frontend engine, every endpoint, persistence, NASA, Nova privacy
```

## Deployment

`Dockerfile`: slim Python 3.12, non-root, pinned `requirements.lock`, health check on `/health`, honours `$PORT`.
Set `NASA_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `CORS_ORIGINS` (include the deployed frontend),
and optionally `GEMINI_API_KEY`. Run [`supabase/schema.sql`](supabase/schema.sql) once. Row Level Security is **off**,
so never ship the project's anon key in a frontend. Without Supabase the app uses an in-memory store.

## Known limitations

- Crew data is simulated; thresholds are illustrative decision support, not medical advice.
- No authentication or rate limiting (prototype); the acting flight surgeon is a fixed name.
- The Docker image build was not verified in this environment (the container command and health check were).

## Sources

NASA [Human Body in Space (RIDGE)](https://www.nasa.gov/humans-in-space/the-human-body-in-space/) ·
[DONKI API](https://ccmc.gsfc.nasa.gov/DONKI/api/) · [JPL Horizons API](https://ssd-api.jpl.nasa.gov/doc/horizons.html) ·
[Radiation protection brief](https://www.nasa.gov/wp-content/uploads/2023/03/radiation-protection-technical-brief-ochmo.pdf) ·
CO₂ briefs ([1](https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-004-carbon-dioxide.pdf), [2](https://nasa.gov/wp-content/uploads/2023/03/co2-technical-brief-ochmo.pdf)) ·
[ECLSS brief](https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-002-eclss.pdf) · [Gemini API](https://ai.google.dev/gemini-api/docs).

## Use of AI

Parts of this backend were written with AI assistance (Claude Code) and reviewed by the team.

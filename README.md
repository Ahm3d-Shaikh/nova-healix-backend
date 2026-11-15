# Nova Healix: backend

FastAPI backend for **Nova Healix**, a crew health monitor for a 4-person Mars transit, organised around NASA's
five hazards of human spaceflight (**R**adiation, **I**solation, **D**istance, **G**ravity, **E**nvironment).
Built for NASA Space Apps 2026 — *Create Health Monitoring Software for Astronauts on Space Missions*.

> **Decision support prototype, not a medical device. Crew data is simulated. Space weather (NASA DONKI) and
> distance (NASA JPL Horizons) can be real NASA data.**

- **Live API docs (Swagger):** https://nova-healix-backend-production.up.railway.app/docs
- **What changed and every API, for the frontend team (one file):** [docs/BACKEND_UPDATE.md](docs/BACKEND_UPDATE.md)
- **Build tracker (every endpoint and rule, with status):** [docs/V2_TRACKER.md](docs/V2_TRACKER.md)
- **Contract (types, endpoints, rules):** the v2 guide in the frontend repo
  [hashir4825/Nova-Helix](https://github.com/hashir4825/Nova-Helix) → `docs/BACKEND_API_GUIDE.md`
- Earlier RIDGE app (superseded, kept for history): [docs/archive/ridge/](docs/archive/ridge/)

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
- **Mobility & Balance Check** (extra endpoints, see [docs/BACKEND_UPDATE.md](docs/BACKEND_UPDATE.md)): three short movement tests measured in the browser with MediaPipe; results feed the Gravity hazard and a finding. Test page at `/demo/mobility/`.
- **ECHO** (Ahmed's scored isolation check-in chat), **distance**, a one-call **dashboard** and **alerts**: all on the same core, feeding the Isolation hazard and findings.
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

One crew, one clock, one engine, one database. Pure logic is separate from HTTP and from storage.

```text
app/
├── main.py            # create_app(): routers, CORS (GET/POST/PUT), error mapping, startup
├── container.py       # builds and wires everything (the one container)
├── api/deps.py        # FastAPI dependency
├── core/              # settings, domain errors, logging, middleware
├── domain/            # pure logic, no I/O: seeded generator, data store, scoring engine (engine/hazards,
│                      #   insights/, interpret), Nova rules, ECHO and mobility scoring
├── schemas/           # pydantic models = the frontend's types (camelCase on the wire)
├── services/          # clock, telemetry, analysis, crew mode, Nova, ECHO, mobility, actions, overview, Gemini wrapper
├── repositories/      # write-through persistence (state, echo) and the external-feed cache
├── nasa/              # DONKI and JPL Horizons clients, parsers, feed service, mapping onto the mission
├── db/                # Supabase (PostgREST) and in-memory backends
├── routers/           # thin HTTP endpoints
├── static/mobility/   # MediaPipe test page for the Mobility & Balance Check
└── data/              # data exported from the frontend, real DONKI snapshot
supabase/              # schema.sql (the one schema), cleanup_old_tables.sql (optional)
scripts/               # check_donki_live, build_snapshot, frontend-golden (regenerate the parity fixtures)
tests/                 # pytest: parity with the frontend engine, every endpoint, ECHO, mobility, persistence, NASA
```

## Deployment

`Dockerfile`: slim Python 3.12, non-root, pinned `requirements.lock`, health check on `/health`, honours `$PORT`.
Set `NASA_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `CORS_ORIGINS` (include the deployed frontend),
and optionally `GEMINI_API_KEY`. Run [`supabase/schema.sql`](supabase/schema.sql) once (one schema for everything). Row Level Security is **off**,
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

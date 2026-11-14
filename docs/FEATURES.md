# RIDGE Monitor Backend — Features Built So Far

Status as of 14 Nov 2026 (hackathon day 1). Stack: FastAPI + Pydantic. Product brief: [RIDGE_CONTEXT.md](RIDGE_CONTEXT.md).

> **Decision support prototype, not a medical device. Crew data is simulated; space-weather data is real NASA data.**

## 1. What the backend does

It serves a crew health dashboard organised around NASA's five spaceflight hazards
(**R**adiation, **I**solation, **D**istance, **G**ravity, **E**nvironment) plus **Mirror Gap**,
which checks whether an astronaut's self-assessment can be trusted. For a simulated crew of three
over a 30-day mission, it runs a rules engine and returns green / amber / red cards, alerts with
*what / why / action / source*, and the numbers behind each card.

## 2. Feature list

### Live NASA space weather (DONKI)
- Fetches SEP, flares, CME, geomagnetic storms and notifications for a real storm episode (8–12 May 2024), inserted into the mission on **day 20**.
- Three-tier fallback: **live** (cached 1 h) → **cached copy** → **bundled snapshot** (`app/data/donki_snapshot.json`, a real saved response). The response always says which `source` it used and why (`reason`).
- Rate-limit aware: a 429 is detected, never retried, and backed off. Timeouts and 5xx errors are retried twice.
- `/DONKI/FLR` currently returns 404 on api.nasa.gov, so flares are derived from DONKI notifications automatically.
- Cache is warmed at startup so the first dashboard request is fast.
- Verified live with a personal key: `python -m scripts.check_donki_live`.

### RIDGE rules engine (pure functions, no I/O)
| Card | Rules |
|---|---|
| **R** Radiation | SEP in last 24 h → red · X-class flare or CME in 24 h → amber · cumulative dose vs 600 mSv (≥80 % amber, ≥95 % red) · 250 mSv per-event limit · neutron share estimate |
| **I** Isolation | Three-Item Loneliness Scale: 3–5 green, 6–9 amber, ≥7 for 3 days red |
| **D** Distance | Mission comms delay (ISS 0 s, Moon ≈1.3 s, Mars 3–22 min); amber when running on cached/snapshot data or Deep space mode |
| **G** Gravity | Baseline = days 1–7 (mean ± SD); HR/BP above mean + 2 SD for 3 days → amber "flag for review"; exercise missed 2 days → amber; both → red |
| **E** Environment | CO₂ 7-day avg > 2.5 mmHg amber, 1-h > 3 mmHg red; cabin temp outside 18–27 °C amber |
| **Mirror Gap** | `gap = z_self − z_performance` vs first 5 sessions; gap > 1.0 on 2 days amber, > 1.5 red; lapse bands (<11 good, 11–19 reduced, ≥20 poor) |

Card level = worst of its rules. Every threshold lives in `app/rules/thresholds.py`, tagged `[NASA]`, `[CSA]`, `[PAPER]` or `[OURS]` (ours are shown as *illustrative*).

### Simulated crew (seeded, 30 days each)
- **A** healthy · **B** sleep-deprived from day 18 (slow reactions while self-rating stays 7–8 → Mirror Gap amber → red) · **C** cardiovascular drift + isolation from day 10 (Gravity and Isolation amber → red).
- Real SEP days drive simulated dose spikes, so all three get a radiation alert together on day 20.
- Verified day by day: A stays green outside the storm, B and C follow their scripted stories.

### Dashboard-ready API
| Endpoint | Purpose |
|---|---|
| `GET /api/dashboard?day=N` | One call: settings, data-source status, last-24 h events, every astronaut's 6 cards (level + typed metrics + rule results), alert panel |
| `GET /api/timeline?astronaut=` | Card levels for all 30 days — powers the day slider and history charts; real storm days included |
| `GET /api/crew`, `/api/crew/{id}?day=N` | Crew summary and detail with daily records and Mirror Gap series |
| `GET /api/alerts?day=N` | All amber/red alerts, worst first |
| `GET /api/space-weather` | Normalised DONKI events with `mission_day`, `source`, `data_as_of`, `reason` |
| `POST/GET /api/mirror-gap/{id}` | Score a reaction test (self-rating + times) → lapses, false starts, gap, level; plus history |
| `GET /api/isolation/questionnaire`, `POST/GET /api/isolation/{id}` | Loneliness check-in form definition, scoring and history |
| `GET/POST /api/settings` | Mission (ISS/Moon/Mars), Deep space mode, current mission day |
| `GET /api/meta` | Disclaimer, real-vs-simulated data, every threshold's provenance, sources |
| `POST /api/demo/reset` | Reset to day 5 / Mars / live and clear submissions (repeatable demo) |
| `GET /health`, `GET /` | Liveness and disclaimer |

Card `metrics` are typed and discriminated by `kind` (radiation, isolation, distance, gravity, environment, mirror), so the frontend never parses alert text. Interactive docs at `/docs`.

### Engineering quality
- **Structure:** thin routers → services → pure rules; dependency-injected container; injectable clocks and DONKI client.
- **Errors:** domain errors mapped to HTTP in one place; out-of-range `day` returns 422; bodies are `{"detail": "..."}`.
- **Observability:** `X-Request-ID`, `X-Process-Time-Ms`, access log, security headers, gzip; API key never logged.
- **Performance:** timeline computed levels-only and cached (52 ms → 28 ms cold, 1.8 ms cached); dashboard ≈ 6 ms.
- **Quality gate (`make check`):** ruff lint + format, `mypy --strict`, pytest with coverage ≥ 90 % (currently 56 tests, 98.5 %).
- **Delivery:** GitHub Actions CI, pre-commit, Makefile, minimal pinned `requirements.txt` + full `requirements.lock`, non-root Docker image with health check.

## 3. Branch history

| Branch | Delivered |
|---|---|
| `feature/ridge-backend` | RIDGE rules engine, DONKI client, crew generator, core endpoints, live-DONKI hardening |
| `feature/dashboard-data` | `/api/dashboard`, `/api/timeline`, card metrics, isolation check-in |
| `feature/requirements-coverage` | `/api/meta` (disclaimer + threshold provenance + sources), JSON persistence, demo reset, isolation trend, card headlines, offline fetch budget, requirements + coverage docs |
| `feature/production-hardening` | Central thresholds, typed metrics, error handling, middleware, caching, tooling, CI, Docker |

All merged into `development` and `main`.

## 4. Known limitations (deliberate for the hackathon)

- Settings (mission, day, deep-space mode) are one process-wide demo state, not per user.
- Submitted Mirror Gap and isolation check-ins are saved to JSON files (`SUBMISSIONS_DIR`) but do not change the simulated cards or alerts.
- No authentication or rate limiting; CORS limited to configured origins; routes are `/api/...` without a version prefix.
- Docker image build not yet verified (Docker daemon was off); the container start command and health check were verified directly.
- Not built: Angular frontend, PDF export, real OSDR RadLab dose data, Mission Control view.
- The official challenge "Resources" list still needs a manual review (see the brief).

## 5. Run it

```bash
make install && cp .env.example .env   # set NASA_API_KEY
make run                               # http://127.0.0.1:8000/docs
make check                             # lint + types + tests
python -m scripts.check_donki_live     # verify live NASA access
```

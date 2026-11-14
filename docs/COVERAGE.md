# Requirements Coverage — Backend

Maps every requirement in [REQUIREMENTS.md](REQUIREMENTS.md) to what the backend does today.
Legend: ✅ done and tested · 🟡 backend ready, needs the frontend · ⬜ not built.

Verified on 14 Nov 2026 against the running app with a live NASA key (acceptance results in §5).

## 1. Functional requirements

| Req | Status | Where |
|---|---|---|
| FR-01 3 astronauts × 5 cards + overall | ✅ | `GET /api/dashboard` (also `/api/crew`) |
| FR-02 card = worst of its rules | ✅ | `app/rules/engine.py` |
| FR-03 day slider 1–30 | ✅ | `?day=N` on every read endpoint; `GET /api/timeline` returns all 30 days in one call. Slider UI itself: 🟡 |
| FR-04 radiation data badge | ✅ | `space_weather.source` (`live` / `cached` / `snapshot`) + `reason`; radiation card `metrics.data_source` |
| FR-05 every amber/red creates an alert | ✅ | `alerts` in dashboard and detail, `GET /api/alerts` |
| FR-06 alert fields (hazard, level, what, why, action, source) | ✅ | `Alert` model; test checks all fields non-empty |
| FR-07 red first, then amber | ✅ | `engine.flagged_alerts`, `CrewService.alerts` |
| FR-08 DONKI SEP / FLR / CME / GST / notifications | ✅ | `donki_client.py`; `/DONKI/FLR` is down upstream (404), flares derived from notifications automatically |
| FR-09 cumulative dose + neutron estimate | ✅ | radiation card `metrics` (`percent_of_limit`, `neutron_dose_estimate_msv`, …) |
| FR-10 loneliness check with trend | ✅ | `GET /api/isolation/questionnaire`, `POST/GET /api/isolation/{id}`; card `metrics.trend` (rising / falling / stable) and `history` |
| FR-11 mission setting + comms delay | ✅ | `GET/POST /api/settings` (`comms_delay`), distance card |
| FR-12 deep space mode | ✅ | `deep_space_mode` setting or `?deep_space_mode=`; serves cache/snapshot, Distance amber |
| FR-13 HR/BP vs own baseline | ✅ | gravity card `metrics.resting_hr / sys_bp / dia_bp` (value, baseline, threshold) |
| FR-14 missed exercise | ✅ | `exercise_missed_days` |
| FR-15 CO₂ 1 h / 7 d + temperature | ✅ | environment card `metrics` |
| FR-16 self-rating 1–10 | ✅ validated server-side · 🟡 form in UI | `MirrorGapSubmission` |
| FR-17 3-min PVT-B scoring | ✅ scoring · 🟡 the timed test screen | `POST /api/mirror-gap/{id}` → mean RT, speed, lapses, false starts, band |
| FR-18 60-s demo mode, not validated | ✅ | `mode: "demo_60s"` → `validated: false`, no lapse band |
| FR-19 gap vs first 5 sessions + alert | ✅ | `app/rules/mirror_gap.py` |
| FR-20 save results, show history | ✅ | JSON-file persistence survives restarts (`SUBMISSIONS_DIR`, default `var/`); `GET /api/mirror-gap/{id}` |
| FR-21 seeded 30-day simulation | ✅ | `app/services/crew_generator.py` (seed in config) |
| FR-22 one real DONKI event in the timeline | ✅ | storm on day 20 (`storm_days` = 20–22) |
| FR-23 disclaimer on every page | ✅ API · 🟡 UI | `GET /api/meta`, `disclaimer` in `/api/dashboard`, in `/` and OpenAPI description |

## 2. Technical requirements

| Req | Status | Notes |
|---|---|---|
| TR-01 key in env var, never in browser | ✅ | `NASA_API_KEY`; only the backend calls NASA; key never logged |
| TR-02 1 h cache + snapshot fallback | ✅ | live → cache → snapshot; also overall 12 s fetch budget so a dead network never blocks |
| TR-03 rules in Python, one module, unit tests | ✅ | `app/rules/`, 71 tests, 98 %+ coverage |
| TR-04 in-memory + JSON files | ✅ | `app/services/store.py` (JSON file store; SQLite not needed) |
| TR-05 – TR-07 Angular pages, charts, `performance.now()` | ⬜ | frontend not part of this repo |
| API table (7 endpoints) | ✅ | all present, plus dashboard, timeline, isolation, meta, demo reset |

## 3. Non-functional requirements

| Req | Status | Notes |
|---|---|---|
| NFR-01 works offline | ✅ | snapshot fallback; tested with failing and hanging networks |
| NFR-02 alert clear in 5 s | 🟡 | every alert has short what / why / action; UI wording to be checked |
| NFR-03 repeatable demo | ✅ | fixed seed; `POST /api/demo/reset` returns to day 5 / Mars / live and clears submissions |
| NFR-04 not colour alone | ✅ API · 🟡 UI | each card has a `level` word and a plain-text `headline` |
| NFR-05 every threshold shows source or "illustrative" | ✅ | `GET /api/meta` → `thresholds[]` with provenance (`nasa`, `csa`, `published_method`, `illustrative`); every alert's `source` text; tests enforce it |

## 4. Decision rules (section 7)

All 14 rule rows are implemented in `app/rules/*` with values in `app/rules/thresholds.py`; each is tagged NASA / CSA / paper / ours and exposed through `/api/meta`.

## 5. Acceptance criteria — verified

| Criterion | Result |
|---|---|
| Day 5: all three green | ✅ all 18 cards green with live data |
| Real DONKI event day: all get a radiation alert | ✅ day 20: A, B, C radiation red |
| Day 25: C shows Gravity and Isolation alerts | ✅ both red, with why / action / source |
| Day 25: B shows a Mirror Gap warning | ✅ red |
| Deep space mode: app works, shows cached data | ✅ `source: cached`, `reason: deep_space_mode`, Distance amber |
| Judge can take the Mirror Gap test live | ✅ backend (submit → gap + level) · 🟡 test screen |
| Disclaimer visible on every page | ✅ API · 🟡 UI |
| README lists sources + use-of-AI note | ✅ |

## 6. Still open

- **Frontend (Angular)** — all UI items marked 🟡 / ⬜ above, including the timed PVT-B screen.
- **Nice-to-haves** — Mission Control view (data exists in `/api/dashboard`), PDF report export, real OSDR RadLab dose.
- **Official challenge Resources list** — someone must read it on the challenge page and map any listed dataset.
- **Demo deliverables** — slides, 30-second video, demo script.
- **Verify the Docker image build** — the daemon was off here; start command and health check were verified directly.
- **Known limitations** — one shared demo state (not per user); no auth (out of scope per the requirements).

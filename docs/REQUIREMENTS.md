# Nova Healix — Requirements Document

NASA Space Apps 2026 · Create Health Monitoring Software for Astronauts on Space Missions · updated 15 Nov 2026
(previously "RIDGE Monitor"; the earlier version is kept in `docs/archive/ridge/REQUIREMENTS.md`)

**Status legend:** ✅ built and tested · 🔁 changed from the earlier version · ➖ dropped · 🖥️ frontend's job (not verifiable from the backend) · ⏳ not built yet

## 0. What changed since the earlier version

| Earlier (RIDGE Monitor) | Now (Nova Healix) |
|---|---|
| 3 astronauts (A, B, C), 30 mission days, a day slider | **4 astronauts** (Hashir, Ahmad, Hannan, Sabaina), a **260-day Mars transit**, **mission hours** and a live clock; the past can be viewed with `?at=` |
| Cards with green / amber / red and rule alerts | Each hazard gets a **0–100 score with weighted drivers**, status **nominal / watch / alert**, and a plain-language explanation. Alerts became **findings** with evidence and recommended actions |
| Fixed thresholds against a population | **Personal baselines**: each astronaut is compared with their own normal range |
| Mirror Gap test (self-rating vs reaction test) | ➖ **Dropped** (the frontend's v2 contract removed it). Reaction time stays as a weekly measurement that feeds the Isolation hazard and the sleep finding |
| Mission setting ISS / Moon / Mars and "deep space mode" | One mission (Mars). "Deep space mode" became the **`autonomous`** flag (Earth link lost) |
| Daily 3-question loneliness form | **ECHO** (scored AI check-in chat) plus **Nova** (private companion, nothing stored) plus daily check-in and questionnaires |
| JSON files / in-memory storage | **Supabase (Postgres)** with an in-memory fallback; one schema, 14 tables |
| Two systems (RIDGE app and v2) | **One system**: one crew, clock, engine and database |
| New | Nova, Crew Mode, Mission Control actions and messages, Mobility & Balance Check, real NASA JPL Horizons distance |

## 1. Overview

Nova Healix is a crew health monitor for a 4-person Mars transit, organised around NASA's five spaceflight hazards
(Radiation, Isolation, Distance, Gravity, Environment). It scores each hazard for each astronaut against their own
baseline, raises findings with evidence and actions, and gives astronauts a private companion and short check-ins.

**Problem:** on long missions astronauts must spot health changes in themselves and act without real-time help from Earth.
**Solution:** hazard scores and findings for Mission Control; a private companion (Nova) and quick check-ins for the astronaut;
real NASA space-weather and distance data.
**Stack:** Angular frontend ([Nova-Helix](https://github.com/hashir4825/Nova-Helix), Vercel) + FastAPI backend (Railway) + Supabase.
**Event:** 14–15 Nov 2026; judging starts 16 Nov.

## 2. Goals

| # | Goal | How we measure it | Status |
|---|---|---|---|
| G1 | Help astronauts and Mission Control spot, evaluate and act on health changes | Every finding shows a summary, why it matters, evidence and recommended actions | ✅ |
| G2 | Stand out from vitals-only dashboards | Personal baselines, five-hazard scoring, a privacy-first companion with a safety exception, a camera-based Mobility & Balance Check | ✅ (Mirror Gap dropped) |
| G3 | Use real NASA data | Real DONKI storm replayed on mission day 97; real JPL Horizons Earth–Mars distance sets the trajectory | ✅ |
| G4 | Be scientifically valid | Thresholds are labelled illustrative unless a source is cited; ECHO uses a validated scale | 🔁 see section 7 |
| G5 | Win on presentation | Working live demo, 2-minute script, 30-second video | ⏳ video and slides |

## 3. Judging alignment

| Criterion | Our answer |
|---|---|
| Impact | Supports crew autonomy for Moon and Mars missions, including a lost-link mode |
| Creativity | Private companion that shares nothing except a content-free safety alert; browser-only movement check; personal baselines |
| Validity | Real NASA data; validated Three-Item Loneliness Scale (ECHO); engine checked against the frontend's reference engine by tests; thresholds we invented are marked illustrative |
| Relevance | Built on NASA's own RIDGE hazard framework |
| Presentation | Mission Control overview, clear findings, real-data labels |

The project must be submitted to the official challenge, not "Create Your Own Challenge". Best Use of Data: DONKI and Horizons.

## 4. Scope

**In scope (built):** five hazard scores for 4 crew · findings panel · crew summaries · personal baselines and per-metric readings ·
Crew Mode (daily check-in, questionnaires) · Nova (private companion) · ECHO (scored check-in chat) · Mission Control actions,
messages with signal delay, resolve / reopen · Mobility & Balance Check · live NASA DONKI with offline snapshot · NASA Horizons distance ·
distance, dashboard and alerts views · simulated crew with a fixed seed.

**Nice-to-have:** per-hazard history chart ✅ (`hazards/{hazard}/history`) · Mission Control view 🖥️ · PDF crew report ⏳ · real ISS dose data from NASA OSDR RadLab ⏳.

**Out of scope:** real astronaut data or wearable hardware · medical diagnosis or treatment advice · user accounts and authentication.

## 5. Users

| User | Needs |
|---|---|
| Astronaut | See own status, do a daily check-in and questionnaires, talk privately to Nova, run the movement check |
| Crew medical officer (Sabaina) | See all crew, review flagged readings |
| Flight surgeon / Mission Control (Haleem) | See findings, message the crew (with the real signal delay), log actions, resolve findings |
| Judges (demo) | Understand the value in under 2 minutes |

## 6. Functional requirements

### Overview and time
| ID | Requirement | Status |
|---|---|---|
| FR-01 | Show 4 astronauts, each with 5 hazard scores and an overall status | ✅ `GET /api/assessment/hazards`, `/crew-summaries` |
| FR-02 | A hazard's status comes from its 0–100 score: 70 and above alert, 40 and above watch | 🔁 replaces "worst of its rules" |
| FR-03 | Everything can be evaluated at any past mission hour (`at`); never later than now | 🔁 replaces the day slider |
| FR-04 | Mark what is real NASA data | 🔁 partial: events carry `source: "NASA DONKI"`; `trajectorySource` and distance `source` say "NASA JPL Horizons". The live / cached / snapshot state of DONKI is logged but not returned by the API |

### Findings (were "alerts")
| ID | Requirement | Status |
|---|---|---|
| FR-05 | Rules raise findings with severity info, watch or alert; a resolved finding returns if it gets worse | ✅ `GET /api/insights` |
| FR-06 | Each finding shows title, summary, why it matters, evidence (value against personal baseline), confidence and recommended actions | ✅ (no separate per-finding "source" field; sources are in the docs and metric catalogue) |
| FR-07 | Sort: Nova safety alerts first, then severity, then newest | ✅ |
| FR-05b | Mission Control can log actions, message the astronaut, resolve and reopen findings | ✅ `/api/actions`, `/messages`, `/insights/{id}/resolve` and `/reopen` |

### Radiation (R)
| ID | Requirement | Status |
|---|---|---|
| FR-08 | Fetch DONKI events (SEP, flares, CME, geomagnetic storms, notifications) and replay the real storm on mission day 97 | ✅ 18 events (every SEP, X-class flares, Kp 7+) on `GET /api/mission/events` |
| FR-09 | Track cumulative dose against the 600 mSv career limit | ✅ (neutron-share estimate ➖ dropped) |

### Isolation (I)
| ID | Requirement | Status |
|---|---|---|
| FR-10 | Daily loneliness check scored 3–9 (Three-Item Loneliness Scale), with history | 🔁 **ECHO**: chat, then a score; `GET /api/isolation/{id}` is the history |
| FR-10b | A private companion (Nova): stateless, nothing stored, logged or scored | ✅ |
| FR-10c | Safety exception: self-harm or acute medical red flags get a pre-written reply and a content-free alert for the flight surgeon | ✅ verified end to end |
| FR-10d | Daily check-in (one per astronaut per day) and four questionnaires (wellbeing, sleep, workload, team) | ✅ |

### Distance (D)
| ID | Requirement | Status |
|---|---|---|
| FR-11 | Signal delay to Earth from the mission trajectory (real Horizons distance at the Mars end) | 🔁 replaces the ISS / Moon / Mars setting |
| FR-12 | Lost-link mode | 🔁 `autonomous=true` raises the Distance score; offline fallbacks keep the API working |

### Gravity (G)
| ID | Requirement | Status |
|---|---|---|
| FR-13 | Compare resting heart rate, blood pressure and other vitals with each astronaut's own baseline | ✅ `…/metrics/{metric}/baseline`, readings in `…/interpretation` |
| FR-14 | Track exercise and flag missed sessions; track bone, muscle and strength change | ✅ finding `exercise:<crew>` |
| FR-14b | Mobility & Balance Check (balance, 5× sit-to-stand, squat knee bend), measured in the browser, scored by the backend; feeds the Gravity score and a finding | ✅ backend · ⏳ Angular page |

### Environment (E)
| ID | Requirement | Status |
|---|---|---|
| FR-15 | Monitor cabin CO₂, noise, temperature, humidity and SpO₂ | 🔁 CO₂ 3-day mean drives the score; crew finding when the 2-day mean is above 3 mmHg (alert at 4) |

### Mirror Gap
| ID | Requirement | Status |
|---|---|---|
| FR-16 to FR-20 | Self-rating, 3-minute PVT-B test, demo mode, gap against the first 5 sessions, history | ➖ **Dropped** in the v2 contract. A weekly reaction-time measurement remains (simulated) |

### Simulation
| ID | Requirement | Status |
|---|---|---|
| FR-21 | Generate crew data with a fixed seed so the demo repeats exactly | ✅ 4 astronauts, 146 days, hourly vitals; identical to the frontend's built-in demo data (tests compare them) |
| FR-22 | Insert a real DONKI event into the mission timeline | ✅ day 97 |

### Disclaimer
| ID | Requirement | Status |
|---|---|---|
| FR-23 | Show: "Decision support prototype, not a medical device. Crew data is simulated. Space weather (NASA DONKI) and distance (NASA JPL Horizons) can be real NASA data." | ✅ API root, Swagger and `GET /api/dashboard` · 🖥️ every page |

### Extra APIs
| ID | Requirement | Status |
|---|---|---|
| FR-24 | `GET /api/distance`: Earth distance and signal delay for each mission day | ✅ |
| FR-25 | `GET /api/dashboard` (one call for an overview) and `GET /api/alerts` (active watch and alert findings) | ✅ |

## 7. Decision rules

All thresholds that are ours are **illustrative design choices** and must be labelled that way in the app.

**Hazard score** = `round(0.4 × worst driver + 0.6 × weighted average of drivers)`, limited to 0–100. A driver measured against a
baseline contributes `clamp(z × 45, 0, 100)`, where z is the distance from the personal mean in units of half the normal band.

| Hazard | Drivers (weight) |
|---|---|
| Radiation | cumulative dose vs 600 mSv limit (.55), excess over crew median (.25), dose rate last 3 h (.12), lymphocytes (.08) |
| Isolation | mood 7-day (.22), stress (.22), HRV (.16), sleep efficiency (.14), reaction time (.11), missed check-ins (.15), ECHO loneliness (.12, when a check-in exists) |
| Distance | workload (.32), stress under autonomy (.16), signal delay or lost link (.22), symptoms needing Earth consult (.15), medical supply readiness (.15) |
| Gravity | bone density change (.24), lean mass (.14), leg strength (.10), fluid-shift symptoms (.24), near vision (.12), systolic BP (.08), back pain (.08), Mobility check (.12, when a check exists) |
| Environment | CO₂ 3-day (.32), sleep efficiency (.18), night noise (.14), SpO₂ (.10), white blood cells (.10), headache or congestion reports (.16) |

**Findings (triggers):**

| Finding | Trigger | Severity |
|---|---|---|
| `sleep-debt` | 5-night sleep at least 1.0 h below personal baseline | watch; alert at 2 h (1.8 h with an EVA within 5 days) |
| `isolation-stress` | 3 or more of 5 signals moving the same way (mood, stress, HRV, check-ins, sleep) | watch; alert at 4 or more |
| `rad-outlier` | highest dose and at least 8% above the crew median | watch |
| `fluid-shift` | 3 headaches in 7 days, or any vision change | watch |
| `exercise` | 4 or more missed sessions in 14 days | watch |
| `workload` | weekly score 65 or more and above baseline | info |
| `checkin` | latest check-in has mood 2 or lower, nausea, back pain or other | watch or info |
| `co2:crew` | crew 2-day CO₂ mean above 3 mmHg | watch; alert at 4 |
| `bone-on-track` | bone loss within the −0.5 %/month target | info |
| `q:<assignment>` | submitted questionnaire; score 60 or more | watch |
| `mobility:<crew>` | latest Mobility check flagged | watch or alert |
| `loneliness:<crew>` | latest ECHO score elevated or with a safety concern | watch or alert |
| `note:<id>` | a note the astronaut chose to share | info |
| `safety:<id>` | Nova safety exception (category and signal only) | alert, always first |

**ECHO scoring** (Three-Item Loneliness Scale, Hughes et al. 2004): score 3–9. 3–5 nominal; 6 or more watch; 7 or more on 3 consecutive days, or a
safety concern, alert. A rating with confidence below 0.6 is stored but ignored and capped at watch; a safety concern is always shown.

**Mobility & Balance Check** (ours, illustrative): balance hold under 10 s watch, under 5 s alert · 5 sit-to-stands 12 s / 15 s · squat knee bend under
100° / 80° · 25% / 50% worse than the astronaut's own first check · pose confidence below 0.6 is not used. It measures movement, not bone health.

## 8. Data requirements

| Data | Real or simulated | Source |
|---|---|---|
| Space-weather events | Real | NASA DONKI API (live, 1-hour cache, bundled snapshot) |
| Earth–Mars distance at arrival | Real | NASA JPL Horizons (cached; smooth model curve if unavailable) |
| Radiation, CO₂, temperature limits | Real (published) | NASA-STD-3001 and NASA briefs |
| Loneliness scale | Real (validated) | Hughes et al., 2004 |
| Crew vitals, sleep, dose, CO₂, noise, labs, bone and muscle, check-ins | Simulated | Our seeded generator (same as the frontend's) |

**Metrics (29):** vitals (HR, HRV, SpO₂, temperature, blood pressure, respiration; hourly), sleep duration and efficiency, radiation dose and
dose rate, bone density, muscle mass, leg strength, mood, energy, sleep quality, stress, workload, reaction time, vision, white blood cells,
lymphocytes, bone marker, CO₂, noise, cabin temperature and humidity, medical supply readiness.

**Stored at runtime (Supabase):** check-ins, questionnaire answers and scores, Nova safety flags (category and signal only) and shared notes,
Mission Control action log, messages and resolutions, Mobility checks, ECHO sessions, messages and scores, and the launch time. **Nova chat is never stored.**
ECHO transcripts are stored by design (a separate, explicit check-in).

### Simulated crew (as built)
| Astronaut | Story | Expected at day 142, 14:00 |
|---|---|---|
| Hashir (commander) | Steady reference case | all nominal |
| Ahmad (flight engineer) | Sleep debt before EVA-3, high workload | watch (Isolation 57, Distance 54) |
| Hannan (mission specialist) | Isolation stress, skipped exercise, falling mood | **alert** (Isolation 87) |
| Sabaina (medical officer) | Highest dose after late shelter entry, fluid-shift symptoms | watch (Gravity 68, Radiation 45) |

## 9. Technical requirements

### Backend (FastAPI)
| ID | Requirement | Status |
|---|---|---|
| TR-01 | NASA key in the environment (`NASA_API_KEY`); never exposed to the browser | ✅ |
| TR-02 | Cache DONKI for 1 hour; fall back to `app/data/donki_snapshot.json` | ✅ |
| TR-03 | Simulation and all rules in Python, in pure-logic modules, with unit tests | ✅ engine tests compare against the frontend's engine |
| TR-04 | Storage | 🔁 Supabase (Postgres), in-memory fallback; one schema file `supabase/schema.sql`, 14 tables |
| TR-08 | Quality gate | ✅ ruff, strict mypy, 216 tests, about 95% coverage, in CI |
| TR-09 | Deployment | Docker image on Railway; frontend on Vercel; `CORS_ORIGINS` includes `https://nova-helix.vercel.app` |

### API endpoints (all JSON, camelCase, times are mission hours)
| Area | Endpoints |
|---|---|
| Mission | `GET /api/mission`, `/api/mission/events`, `/api/crew/{id}/timeline` |
| Crew | `GET /api/crew`, `/api/crew/{id}` |
| Telemetry | `GET /api/crew/{id}/metrics/{metric}` (also `/baseline`, `/interpretation`), `/vitals/live`, `/checkins` |
| Assessment | `GET /api/assessment/hazards`, `/hazards/{hazard}/history`, `/crew-summaries`, `GET /api/insights` |
| Crew Mode | `POST /api/crew/{id}/checkins`, `GET /api/questionnaires`, assignments (`GET`, `PUT …/progress`, `POST …/submit`) |
| Nova | `POST /api/crew/{id}/companion/reply`, `POST /api/crew/{id}/shared-notes` |
| Mission Control | `GET/POST /api/actions`, `GET/POST /api/crew/{id}/messages`, `POST /api/insights/{id}/resolve`, `…/reopen` |
| Mobility | `GET /api/mobility/method`, `POST/GET /api/mobility/{id}` · test page `/demo/mobility/` |
| ECHO | `GET /api/isolation/method`, `POST …/sessions`, `…/messages`, `…/complete`, `GET …/sessions/{sid}`, `GET /api/isolation/{id}` |
| Overview | `GET /api/distance`, `/api/dashboard`, `/api/alerts` |
| Ops | `GET /health`, `GET /` , `/docs` |

Full request and response examples: `docs/BACKEND_UPDATE.md`.

### Frontend (Angular)
| ID | Requirement | Status |
|---|---|---|
| TR-05 | Pages: Mission Control, Crew profile, Insights, Check-in and questionnaires, Nova | 🖥️ built; run against this backend with no errors |
| TR-06 | Charts | 🖥️ ngx-echarts |
| TR-07 | Mobility page with MediaPipe Pose in the browser; PVT with `performance.now()` is no longer needed | ⏳ Mobility page (reference page at `/demo/mobility/`) |

## 10. Non-functional requirements

| ID | Requirement | Status |
|---|---|---|
| NFR-01 | Offline: the API works with no internet (DONKI snapshot, model trajectory) | ✅ |
| NFR-02 | Clarity: any finding is understandable in under 5 seconds | 🖥️ plain-language titles, summaries and explanations come from the backend |
| NFR-03 | Repeatable demo: same simulated data every run | ✅ fixed seed; the mission clock puts "now" on day 142 |
| NFR-04 | Accessibility: status uses colour plus text labels | 🖥️ the API always returns the text status |
| NFR-05 | Transparency: thresholds show a source or the label "illustrative" | 🔁 documented; not every threshold has an in-app source |
| NFR-06 | **Privacy**: Nova conversations are never stored or logged; validation errors never echo what was sent; safety alerts carry no text | ✅ tested |
| NFR-07 | Performance: analysis is cached per quarter hour; a cold full analysis takes about 0.2 s | ✅ |
| NFR-08 | Security: no authentication (prototype); Supabase Row Level Security is off, so the anon key must stay private | known limitation |

## 11. Acceptance criteria

| Criterion | Status |
|---|---|
| At day 142: Hashir nominal, Ahmad watch (sleep debt before EVA-3), Hannan alert (isolation stress), Sabaina watch (fluid shift, highest dose) | ✅ tested and seen in the real frontend |
| The real DONKI storm appears on the timeline around day 97 | ✅ tested |
| `autonomous=true` raises the Distance score | ✅ tested |
| Nova: a safety phrase returns the pre-written reply; Mission Control shows a content-free alert first; resolving works | ✅ verified end to end |
| A daily check-in replaces the same day's earlier one; a submitted questionnaire feeds stress or workload | ✅ tested |
| A Mobility check raises the Gravity score and a finding, with no frontend change | ✅ tested and seen in the real frontend |
| The API still works offline (snapshot, model trajectory) | ✅ tested |
| Disclaimer visible on every page | 🖥️ not verified from the backend |
| The Supabase schema is run in the live project and saving works | ⏳ the 13 new tables are not yet created in the live project |
| A judge can run the Mobility check live | ⏳ Angular page |
| ECHO works with a real Gemini key | ⏳ untested (returns 503 without a key by design) |
| README lists all sources and a use-of-AI note | ✅ |

## 12. Demo script (2 minutes)

1. Mission Control at day 142: four crew, five hazard scores each, one alert (Hannan), findings sorted by urgency.
2. Open Ahmad: "Sleep debt building ahead of EVA-3", with evidence against his own baseline.
3. Timeline: the **real NASA solar storm** on day 97 (DONKI) and the real Earth–Mars distance (Horizons).
4. Nova, privately: ask it to do the check-in and review the card before sending. Then show the safety exception: Mission Control receives only the category, never the words; resolve it.
5. Mobility & Balance Check (when the page is ready): three short tests, and the Gravity score and finding update.
6. Toggle lost-link mode: the Distance score rises; the app keeps working.
7. Close: "Astronauts must judge their own health far from Earth. Nova Healix compares them with their own normal, and keeps their private conversations private."

## 13. Team and timeline

| Area | Owner (as built) |
|---|---|
| Backend: NASA feeds, engine, API, tests | Haleem, Ahmed |
| Supabase, ECHO, Horizons | Ahmed |
| Angular app, Nova screens, Mobility page | Hashir, Sabaina |
| Slides, video, demo script, README | to confirm |
| Integration testing, deployment, submission | to confirm |

Remaining before the deadline: run `supabase/schema.sql` in the live project · set Railway variables (`CORS_ORIGINS`, Supabase, NASA key, optional Gemini key) ·
build the Mobility page · slides and 30-second video · final test, then submit.

## 14. Risks

| Risk | Mitigation |
|---|---|
| DONKI rate limit or outage during judging | Own API key, 1-hour cache, bundled snapshot |
| Judges question medical validity | Cite sources, label illustrative thresholds, show the disclaimer, never diagnose |
| The live site is blocked by CORS | `CORS_ORIGINS` must include `https://nova-helix.vercel.app` (in the code defaults; a Railway variable overrides it) |
| New tables missing in Supabase | Run `supabase/schema.sql`; without it, saves return 503 |
| ECHO stores transcripts (unlike Nova) | Documented as a separate, explicit check-in; use Nova where privacy matters |
| Gemini free-tier limits | Rules-only Nova works without a key; ECHO returns 503 cleanly |
| No authentication | Prototype only; keep the Supabase anon key private |
| Running out of time | Mobility page and video are the open items |
| Official resources list not yet reviewed | One person checks the challenge page and maps any listed dataset |

## 15. Sources

- [Challenge page](https://www.spaceappschallenge.org/2026/challenges/create-health-monitoring-software-for-astronauts-on-space-missions/)
- [Judging & Awards Guide](https://www.spaceappschallenge.org/resources/judging-awards-guide)
- [NASA: The Human Body in Space (RIDGE)](https://www.nasa.gov/humans-in-space/the-human-body-in-space/)
- [NASA DONKI API](https://ccmc.gsfc.nasa.gov/DONKI/api/)
- [NASA JPL Horizons API](https://ssd-api.jpl.nasa.gov/doc/horizons.html)
- [NASA radiation protection brief](https://www.nasa.gov/wp-content/uploads/2023/03/radiation-protection-technical-brief-ochmo.pdf)
- [NASA CO₂ brief](https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-004-carbon-dioxide.pdf) · [CO₂ brief (headache risk)](https://nasa.gov/wp-content/uploads/2023/03/co2-technical-brief-ochmo.pdf)
- [NASA ECLSS brief](https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-002-eclss.pdf)
- [CSA Radi-N2](https://www.asc-csa.gc.ca/eng/sciences/radi-n2.asp)
- [CSA Space Health / Bio-Monitor](https://hdiac.dtic.mil/articles/peak-performance-in-microgravity)
- [Three-Item Loneliness Scale](https://www.phenxtoolkit.org/toolkit_content/supplemental_info/psychosocial/measures/Social_Isolation.doc)
- [PVT-B validation](https://pmc.ncbi.nlm.nih.gov/articles/PMC3197786) · [3-minute PVT lapse bands](https://pmc.ncbi.nlm.nih.gov/articles/PMC3190077)
- [Subjective vs objective gap (NASA JSC)](https://www.24-7pressrelease.com/press-release/414258/clearing-the-space-fog)
- [AURORA (main rival)](https://github.com/fabriciojunio/aurora-astronaut-health)
- [MediaPipe Pose Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker) · [Gemini API](https://ai.google.dev/gemini-api/docs)

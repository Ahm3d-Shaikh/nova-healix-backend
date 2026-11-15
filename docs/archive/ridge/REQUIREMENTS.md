# RIDGE Monitor — Requirements Document

NASA Space Apps 2026 · Create Health Monitoring Software for Astronauts on Space Missions · Nov 14, 2026

See [COVERAGE.md](COVERAGE.md) for how each requirement below maps to the backend, and what is still open.

## 1. Overview

RIDGE Monitor is a crew health dashboard built on NASA's five spaceflight hazards. It flags health risks early and checks whether astronauts can trust their own self-assessment.

- **Problem:** on long missions, astronauts must spot health changes in themselves and act without real-time help from Earth.
- **Solution:** five hazard cards (Radiation, Isolation, Distance, Gravity, Environment), a crew alert panel, and Mirror Gap, which compares how an astronaut feels with how they perform.
- **Stack:** Angular (frontend) + FastAPI (backend).
- **Event:** 14–15 Nov 2026; judging starts 16 Nov.

## 2. Goals

| # | Goal | How we measure it |
|---|---|---|
| G1 | Answer the brief: help astronauts spot, evaluate and act on health changes | Every alert shows what happened, why, what to do |
| G2 | Stand out from vitals-only dashboards | Mirror Gap and RIDGE framework working in the demo |
| G3 | Use real NASA data | Live DONKI space-weather events drive radiation alerts |
| G4 | Be scientifically valid | Every threshold cites a NASA standard or published study, or is labeled illustrative |
| G5 | Win on presentation | Working live demo, 2-minute script, 30-second video |

## 3. Judging alignment

Projects are scored on Impact, Creativity, Validity, Relevance and Presentation. There is also a Best Use of Data award. The project must be submitted to the official challenge, not "Create Your Own Challenge".

| Criterion | Our answer |
|---|---|
| Impact | Supports crew autonomy for Moon and Mars missions |
| Creativity | Mirror Gap: no rival found compares self-rating against test performance |
| Validity | Thresholds from NASA-STD-3001, CSA, validated PVT-B and loneliness scale |
| Relevance | Built on NASA's own RIDGE hazard framework |
| Presentation | Day slider demo, clear alerts, real data badge |

## 4. Scope

**In scope (must-have)**
- Five RIDGE hazard cards with green / amber / red status
- Crew alert panel
- Mirror Gap test and gap calculation
- Simulated crew of 3 over 30 mission days
- Live NASA DONKI data with offline snapshot fallback
- On-screen disclaimer

**Nice-to-have**
- Mission Control view of all crew
- PDF crew report export
- History chart per hazard
- Real ISS dose data from NASA OSDR RadLab

**Out of scope**
- Real astronaut data or wearable hardware
- Medical diagnosis or treatment advice
- User accounts and authentication

## 5. Users

| User | Needs |
|---|---|
| Astronaut | See own status, take daily check-in and Mirror Gap test, get clear actions |
| Crew medical officer | See all crew, review flagged readings |
| Judges (demo) | Understand the value in under 2 minutes |

## 6. Functional requirements

**Dashboard**
- FR-01 Show 3 astronauts, each with 5 RIDGE cards and an overall status.
- FR-02 Each card shows the worst level of its rules.
- FR-03 A mission day slider (1–30) recalculates all statuses and alerts.
- FR-04 The radiation card shows a data badge: Live NASA, Cached, or Snapshot.

**Alerts**
- FR-05 Every amber or red rule result creates an alert.
- FR-06 Each alert shows: hazard, level, what happened, why it matters, action, source.
- FR-07 Alerts are sorted red first, then amber.

**Radiation (R)**
- FR-08 Fetch DONKI events: solar particle events (SEP), flares (FLR), CMEs, geomagnetic storms (GST), notifications.
- FR-09 Track cumulative dose against the career limit and show the estimated neutron share.

**Isolation (I)**
- FR-10 Daily 3-question loneliness check (Three-Item Loneliness Scale), scored 3–9, with a trend.

**Distance (D)**
- FR-11 Mission setting: ISS, Moon or Mars, with its comms delay.
- FR-12 Deep space mode: the app runs fully from cached data.

**Gravity (G)**
- FR-13 Compare resting heart rate and blood pressure to each astronaut's own baseline.
- FR-14 Track exercise and flag missed sessions.

**Environment (E)**
- FR-15 Monitor cabin CO₂ (1-hour and 7-day averages) and temperature.

**Mirror Gap**
- FR-16 Ask "How sharp do I feel?" (1–10) before the test.
- FR-17 Run a 3-minute reaction test (PVT-B); record mean reaction time, response speed, lapses and false starts.
- FR-18 Offer a 60-second demo mode, labeled as not validated.
- FR-19 Compute the gap between self-rating and performance against the person's first 5 sessions, and raise an alert when it is too large.
- FR-20 Save results and show history.

**Simulation**
- FR-21 Generate 30 days per astronaut with a fixed random seed so the demo repeats exactly.
- FR-22 Insert one real DONKI solar event into the mission timeline.

**Disclaimer**
- FR-23 Show on every page: *Decision support prototype, not a medical device. Crew data is simulated; space-weather data is real NASA data.*

## 7. Decision rules

Thresholds marked "ours" are illustrative design choices and must be labeled that way in the app.

| Hazard | Rule | Level | Source |
|---|---|---|---|
| R | Solar particle event in last 24 h | Red: move to shielded area | DONKI; mapping ours |
| R | X-class flare or CME in last 24 h | Amber: watch | DONKI; mapping ours |
| R | Cumulative dose ≥80% / ≥95% of 600 mSv career limit | Amber / Red | NASA-STD-3001; cut-offs ours |
| R | Daily dose ≈0.5 mSv; neutron share ≈30% (≈150 µSv/day) | Shown as estimate | NASA radiation brief; CSA Radi-N2 |
| I | Loneliness score 3–5 / 6–9 | Green / Amber | Three-Item Loneliness Scale |
| I | Score ≥7 for 3 days in a row | Red | ours |
| D | Live data unavailable or deep space mode on | Amber: running on cached data | ours |
| G | HR or BP above baseline + 2 SD for 3 days | Amber: flag for review | ours |
| G | Exercise missed 2 days in a row | Amber | ours |
| G | Both of the above | Red | ours |
| E | CO₂ 7-day average > 2.5 mmHg | Amber | NASA CO₂ brief |
| E | CO₂ 1-hour average > 3 mmHg | Red | NASA-STD-3001 V2 6004 |
| E | Temperature outside 18–27 °C | Amber | NASA ECLSS brief |
| Mirror | Gap > 1.0 on 2 days in a row / > 1.5 | Amber / Red | ours |

**Mirror Gap formula:** `gap = z_self − z_performance`. Performance is mean response speed (1 / reaction time). A positive gap means the astronaut feels sharper than they perform.

**PVT-B rules:** stimulus after a random 1–4 s; a response of 355 ms or slower is a lapse; faster than 100 ms is a false start. Lapse bands for a 3-minute test: under 11 good, 11–19 reduced, 20 or more poor.

## 8. Data requirements

| Data | Real or simulated | Source |
|---|---|---|
| Space weather events | Real | NASA DONKI API |
| Radiation, CO₂, temperature limits | Real | NASA-STD-3001 briefs |
| Neutron share and dose | Real (published) | CSA Radi-N2 |
| Loneliness scale | Real (validated) | Hughes et al., 2004 |
| Reaction test design | Real (validated) | Basner et al., 2011 |
| Crew vitals, sleep, exercise, CO₂, temperature, answers, daily dose | Simulated | Our generator |

Daily record fields: `day, sleep_hours, resting_hr, sys_bp, dia_bp, exercise_min, co2_mmhg_1h, co2_mmhg_7d, cabin_temp_c, loneliness_q1–q3, self_rating, pvt_mean_rt, pvt_lapses, pvt_false_starts, dose_msv`.

**Simulated crew**

| Astronaut | Pattern | Expected result |
|---|---|---|
| A: healthy | Normal variation | All green |
| B: sleep-deprived | From day 18: sleep ≈5 h, lapses 15–22, self-rating stays 7–8 | Mirror Gap amber, then red |
| C: drifting | From day 10: resting HR rises ≈0.5 bpm/day, exercise skipped, loneliness 7–8 | Gravity and Isolation amber, then red |

## 9. Technical requirements

**Backend (FastAPI)**
- TR-01 Store the NASA API key in an environment variable (`NASA_API_KEY`); never expose it to the browser.
- TR-02 Cache DONKI responses for 1 hour; fall back to `data/donki_snapshot.json` on failure or in deep space mode.
- TR-03 Run the simulation and all rules in Python, in one rules module with unit tests.
- TR-04 Storage: in-memory and JSON files; SQLite optional for Mirror Gap results.

**API endpoints**

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/space-weather` | Normalized DONKI events, source (live / cache / snapshot), fetch time |
| GET | `/api/crew` | All astronauts with overall and per-card status |
| GET | `/api/crew/{id}?day=N` | Records up to day N, card statuses, alerts |
| GET | `/api/alerts?day=N` | All amber and red alerts |
| POST | `/api/mirror-gap/{id}` | Submit self-rating and reaction times; returns lapses, gap, level |
| GET | `/api/mirror-gap/{id}` | Mirror Gap history |
| GET / POST | `/api/settings` | Mission type, deep space mode, current day |

DONKI calls use `https://api.nasa.gov/DONKI/{SEP|FLR|CME|GST|notifications}` with `startDate`, `endDate` and `api_key`. Check field names against a live response before writing the parser.

**Frontend (Angular)**
- TR-05 Pages: Crew dashboard, Astronaut detail, Mirror Gap test, Settings.
- TR-06 Charts with ng2-charts (Chart.js) or ngx-echarts.
- TR-07 Measure reaction time with `performance.now()` on `keydown` or `pointerdown` events.

## 10. Non-functional requirements

- NFR-01 Offline: the app works with no internet using the snapshot.
- NFR-02 Clarity: any alert is understandable in under 5 seconds.
- NFR-03 Repeatable demo: same data every run (fixed seed).
- NFR-04 Accessibility: status uses color plus text labels, never color alone.
- NFR-05 Transparency: every threshold shows its source or the label "illustrative".

## 11. Acceptance criteria

- Day 5: all three astronauts green
- Real DONKI event day: all three get a radiation alert
- Day 25: Astronaut C shows Gravity and Isolation alerts with why, action and source
- Day 25: Astronaut B shows a Mirror Gap warning
- Deep space mode on: app still works and shows cached data
- A judge can take the Mirror Gap test live and see a result
- Disclaimer visible on every page
- README lists all sources and a use-of-AI note

## 12. Demo script (2 minutes)

1. Dashboard at day 5: three crew, five hazard cards, all green.
2. Radiation card: "This solar event is real NASA data." Slide to the event day; everyone gets an alert.
3. Astronaut C at day 25: Gravity and Isolation alerts with clear actions.
4. Astronaut B at day 25: rates 8/10 but tests slow; Mirror Gap warns.
5. Turn on deep space mode: the app keeps working.
6. Close: "Astronauts must judge their own health far from Earth. RIDGE Monitor tells them when to trust that judgment."

## 13. Team and timeline

| Person | Owns |
|---|---|
| 1 | FastAPI DONKI client, cache, snapshot, radiation rules |
| 2 | Angular dashboard, RIDGE cards, alert panel |
| 3 | Mirror Gap test and questionnaire (Angular + endpoint) |
| 4 | Crew generator, rules engine, unit tests (Python) |
| 5 | Slides, video, demo script, README |
| 6 | Integration testing, deployment, submission |

- By 2 PM day 1: both app skeletons, DONKI with snapshot, crew generator
- By 10 PM day 1: five cards and alert panel working end to end
- By 12 PM day 2: Mirror Gap working; crew stories visible
- By 4 PM day 2: video, slides, README
- Before deadline: final test, then submit

## 14. Risks

| Risk | Mitigation |
|---|---|
| DONKI rate limit or outage during judging | Own API key, 1-hour cache, snapshot fallback |
| Judges question medical validity | Cite sources, label illustrative thresholds, show disclaimer |
| Running out of time | Build must-haves first; nice-to-haves only after acceptance criteria pass |
| Official resources list not yet reviewed | One person checks the challenge page and maps any listed dataset |

## 15. Sources

- [Challenge page](https://www.spaceappschallenge.org/2026/challenges/create-health-monitoring-software-for-astronauts-on-space-missions/)
- [Judging & Awards Guide](https://www.spaceappschallenge.org/resources/judging-awards-guide)
- [NASA: The Human Body in Space (RIDGE)](https://www.nasa.gov/humans-in-space/the-human-body-in-space/)
- [NASA DONKI API](https://ccmc.gsfc.nasa.gov/DONKI/api/)
- [NASA radiation protection brief](https://www.nasa.gov/wp-content/uploads/2023/03/radiation-protection-technical-brief-ochmo.pdf)
- [NASA CO₂ brief](https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-004-carbon-dioxide.pdf)
- [NASA CO₂ brief (headache risk)](https://nasa.gov/wp-content/uploads/2023/03/co2-technical-brief-ochmo.pdf)
- [NASA ECLSS brief](https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-002-eclss.pdf)
- [CSA Radi-N2](https://www.asc-csa.gc.ca/eng/sciences/radi-n2.asp)
- [CSA Space Health / Bio-Monitor](https://hdiac.dtic.mil/articles/peak-performance-in-microgravity)
- [Three-Item Loneliness Scale](https://www.phenxtoolkit.org/toolkit_content/supplemental_info/psychosocial/measures/Social_Isolation.doc)
- [PVT-B validation](https://pmc.ncbi.nlm.nih.gov/articles/PMC3197786)
- [3-minute PVT lapse bands](https://pmc.ncbi.nlm.nih.gov/articles/PMC3190077)
- [Subjective vs objective gap (NASA JSC)](https://www.24-7pressrelease.com/press-release/414258/clearing-the-space-fog)
- [AURORA (main rival)](https://github.com/fabriciojunio/aurora-astronaut-health)

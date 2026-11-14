# RIDGE Monitor — Development Context (NASA Space Apps 2026)

Handoff brief for the dev team. Stack: Angular (frontend) + FastAPI (backend).
Last updated: 14 Nov 2026 (hackathon day 1).

## 1. The challenge

- **Challenge:** Create Health Monitoring Software for Astronauts on Space Missions (NASA Space Apps 2026, Intermediate; Human Exploration, Software, Space Exploration).
- **Brief in one line:** on long missions astronauts must spot health changes in themselves, then evaluate and act on them. Build software that gathers health indicators and helps them do that.
- **Event:** 14–15 Nov 2026. Submission opened 14 Nov, 9:00 a.m. local time. Judging starts 16 Nov.
- **Judging criteria:** Impact, Creativity, Validity, Relevance, Presentation. Also a "Best Use of Data" award.
- Must submit to the **official challenge** (not "Create Your Own Challenge"), or we lose Global Judging eligibility.
- **Open item:** the official challenge "Resources" list (released 13 Nov) has not been reviewed yet; the site blocks automated reading. Someone should open the challenge page and check whether any listed dataset should be added.

## 2. Competition (why we need a differentiator)

Many teams already published repos for this challenge. Almost all build a vitals dashboard with personal baselines and alerts (e.g. VITA, AstroHealth, VITALS, AstroByte, AETHRA). The strongest rival, [AURORA](https://github.com/fabriciojunio/aurora-astronaut-health), already has: personal baselines, real radiation data (NASA OSDR RadLab, NOAA GOES), offline tablet app, daily check-in, and a 3-minute PVT-B vigilance test.

A vitals dashboard with personal baselines and alerts is the bare minimum, not a differentiator.

**Our differentiators:**

1. **RIDGE framework** — the whole product is organized around NASA's five spaceflight hazards.
2. **Mirror Gap** — compares how the astronaut feels with how they perform on a reaction test, and warns when self-judgment is unreliable. No rival found does this comparison.
3. **Live NASA DONKI space-weather data** driving radiation alerts.

## 3. Product: RIDGE Monitor

**Pitch:** A crew health dashboard built on NASA's five spaceflight hazards. It flags risks early and checks whether astronauts can trust their own self-assessment.

**RIDGE** = **R**adiation, **I**solation & confinement, **D**istance from Earth, **G**ravity fields, hostile/closed **E**nvironments (NASA Human Research Program framework).

### Must-have features

- Five RIDGE hazard cards, each green / amber / red.
- Crew alert panel — every amber/red rule result appears with: what happened, why it matters, what to do, source.
- Mirror Gap — self-rating + 3-minute reaction test (PVT-B) + gap calculation.
- Simulated crew of 3 (A healthy, B sleep-deprived, C cardiovascular drift + isolation), 30 mission days each.
- Disclaimer on screen: *"Decision support prototype, not a medical device. Crew data is simulated; space-weather data is real NASA data."*

### Nice-to-have (only if time allows)

- Mission Control view of all crew
- PDF crew report export
- History chart per hazard
- Real ISS dose data from NASA OSDR RadLab replacing simulated dose

### Do NOT claim

- "Detects heart disease" → say **"flags readings for review"**.
- "Real astronaut vitals" → vitals are simulated.
- Mark all thresholds we invented as **"illustrative"**.

## 4. Data: real vs simulated

| Data | Status | Source |
|---|---|---|
| Space weather events (SEP, flares, CME, storms, notifications) | Real | NASA DONKI API |
| Radiation limits, CO2 and temperature limits | Real | NASA-STD-3001 technical briefs |
| Neutron share and daily neutron dose | Real (published) | CSA Radi-N2 |
| Loneliness questions + scoring | Real (validated scale) | Three-Item Loneliness Scale (Hughes et al., 2004) |
| Reaction test design + lapse rule | Real (validated test) | PVT-B (Basner et al., 2011) |
| Crew vitals, sleep, exercise, CO2/temperature readings, questionnaire answers, daily dose | Simulated | Our generator |

## 5. Rules engine (exact logic)

Each card's status = **worst result of its rules**. Each rule returns:

```json
{ "hazard": "R|I|D|G|E|MIRROR", "level": "green|amber|red", "what": "...", "why": "...", "action": "...", "source": "..." }
```

### R — Radiation

- DONKI SEP event in the last 24 h → **red**, action "move to shielded area". *(our mapping)*
- DONKI X-class flare or CME in the last 24 h → **amber**, "watch". *(our mapping)*
- Cumulative dose vs 600 mSv career limit (NASA-STD-3001): ≥80% amber, ≥95% red *(cut-offs ours)*.
- Per-event limit for solar particle events: 250 mSv (NASA-STD-3001).
- Simulated daily dose baseline ≈0.5 mSv/day (NASA radiation brief), plus a spike on the storm day.
- Show estimated neutron share ≈30% of dose (CSA); ISS neutron dose ≈150 µSv/day (Radi-N2). Label "estimate".

### I — Isolation

Three-Item Loneliness Scale. Questions:

1. "How often do you feel that you lack companionship?"
2. "How often do you feel left out?"
3. "How often do you feel isolated from others?"

Answers: 1 = Hardly ever, 2 = Some of the time, 3 = Often. Sum = 3–9.

- 3–5 → green; 6–9 → amber; ≥7 for 3 consecutive days → red *(red rule ours)*.

### D — Distance

- Mission setting for one-way comms delay: ISS 0 s, Moon ≈1.3 s, Mars 3–22 min (as used by AURORA).
- If live DONKI call fails or "Deep space mode" is on → amber, "running on cached data from `<date>`". App must keep working.

### G — Gravity (cardiovascular flag)

- Baseline per astronaut = mean and SD of days 1–7 for resting HR, systolic BP, diastolic BP.
- Metric > baseline mean + 2 SD for 3 consecutive days → amber "flag for review" *(illustrative)*.
- Exercise missed 2 consecutive days → amber.
- Both together → red.

### E — Environment

- CO2: 7-day average > 2.5 mmHg → amber (keeps headache risk <1%); 1-hour average > 3 mmHg → red (NASA-STD-3001 V2 6004).
- Temperature outside 18–27 °C → amber (NASA ECLSS operating range).

### Mirror Gap

- Test: PVT-B, 3 minutes. Stimulus appears after random 1–4 s; user taps/presses.
- Response ≥ 355 ms = **lapse**. Response < 100 ms = **false start**.
- Record: mean RT, mean 1/RT (response speed), lapses, false starts.
- Optional 60-second "judge demo" mode, labeled as non-validated.
- Self-rating before the test: "How sharp do I feel?" 1–10.
- Lapse bands (3-min PVT, Basner & Rubinstein 2011): <11 good, 11–19 reduced, ≥20 poor.
- **Gap:** z-scores vs the person's first 5 sessions. `gap = z_self - z_performance` (performance = mean 1/RT; higher = better).
- gap > 1.0 on 2 consecutive days → amber: *"You feel sharper than you're performing. Get a crewmate cross-check before critical tasks."* gap > 1.5 → red. *(cut-offs ours)*
- Browser timing: use `performance.now()` and `keydown`/`pointerdown` events; avoid timers for measuring RT.

## 6. Simulated crew spec (30 days each, fixed random seed)

| Astronaut | Programmed pattern | Expected result |
|---|---|---|
| A — healthy | Normal noise around baseline | All green |
| B — sleep-deprived | From day 18: sleep ≈5 h, PVT lapses 15–22, self-rating stays 7–8 | Mirror Gap amber → red |
| C — drifting | From day 10: resting HR +≈0.5 bpm/day, exercise skipped, loneliness score rises to 7–8 | Gravity + Isolation amber → red |

One real DONKI solar event is inserted into the mission timeline so all three get a radiation alert together.

Suggested daily record fields: `day, sleep_hours, resting_hr, sys_bp, dia_bp, exercise_min, co2_mmhg_1h, co2_mmhg_7d, cabin_temp_c, loneliness_q1..q3, self_rating, pvt_mean_rt, pvt_lapses, pvt_false_starts, dose_msv`.

## 7. Architecture (Angular + FastAPI)

### FastAPI (backend)

- Holds the NASA API key in an env var (`NASA_API_KEY`). Get a free key at <https://api.nasa.gov> (`DEMO_KEY` is heavily rate-limited).
- Calls DONKI, caches results (e.g. 1 hour), and falls back to `data/donki_snapshot.json` on failure or when `deep_space_mode=true`.
- Generates the simulated crew (seeded) and runs the rules engine in Python so logic is in one place.
- Storage: in-memory + JSON files is enough; SQLite optional for Mirror Gap results.

Suggested endpoints:

| Method | Path | Returns |
|---|---|---|
| GET | `/api/space-weather?deep_space_mode=false` | Normalized DONKI events + `source: live \| cached \| snapshot` |
| GET | `/api/crew` | List of astronauts with overall + per-card status |
| GET | `/api/crew/{id}?day=N` | Daily records up to day N, card statuses, alerts |
| GET | `/api/alerts?day=N` | All amber/red alerts across crew |
| POST | `/api/mirror-gap/{id}` | Body: self_rating, reaction times[] → returns lapses, false starts, gap, level |
| GET | `/api/mirror-gap/{id}` | Mirror Gap history |
| GET / POST | `/api/settings` | Mission (ISS/Moon/Mars), deep space mode, current mission day |

DONKI endpoints (base `https://api.nasa.gov`): `/DONKI/SEP`, `/DONKI/FLR`, `/DONKI/CME`, `/DONKI/GST`, `/DONKI/notifications` with `startDate`, `endDate` (yyyy-MM-dd), `api_key`. Reference: <https://ccmc.gsfc.nasa.gov/DONKI/api/> — check field names (e.g. flare class, event time) against a live response before coding the parser.

### Angular (frontend)

- Pages: Crew dashboard (3 astronauts × 5 RIDGE cards + alert panel), Astronaut detail (trends), Mirror Gap test, Settings (mission type, deep space mode, day slider for demo).
- Charts: ng2-charts (Chart.js) or ngx-echarts.
- A mission day slider lets judges scrub day 1 → 30 and watch alerts appear.
- Show the data source badge on the radiation card (Live NASA / Cached / Snapshot).

## 8. Demo script (2 minutes)

1. **Dashboard:** three crew members, five hazard cards, all green on day 5.
2. **Radiation card:** "This solar event is real NASA DONKI data." Scrub to the event day — everyone gets a radiation alert.
3. **Astronaut C (day 25):** Gravity and Isolation alerts fire, each with why + action + source.
4. **Astronaut B (day 25):** rates 8/10 but the test is slow → Mirror Gap warning.
5. **Toggle Deep space mode:** the app keeps working from cached data.
6. **Close:** "Astronauts must judge their own health far from Earth. RIDGE Monitor tells them when to trust that judgment."

## 9. Team roles

| Person | Owns |
|---|---|
| 1 | FastAPI DONKI client, cache, snapshot fallback, Radiation rules |
| 2 | Angular dashboard layout, RIDGE cards, alert panel |
| 3 | Angular Mirror Gap test + isolation questionnaire; FastAPI Mirror Gap endpoint |
| 4 | Simulated crew generator + rules engine (Python) + unit tests |
| 5 | Slides, 30-second video, demo script, README sources + disclaimer |
| 6 | Integration testing, deployment, submission |

## 10. Timeline

- By 2 PM day 1: skeleton apps, DONKI working with snapshot, crew generator done.
- By 10 PM day 1: all 5 cards + alert panel working end to end.
- By 12 PM day 2: Mirror Gap working; crew stories visible.
- By 4 PM day 2: video, slides, README with sources + disclaimer + "use of AI" note.
- Before deadline: final end-to-end test, then submit.

## 11. Sources

- Challenge page: <https://www.spaceappschallenge.org/2026/challenges/create-health-monitoring-software-for-astronauts-on-space-missions/>
- Judging guide: <https://www.spaceappschallenge.org/resources/judging-awards-guide>
- NASA RIDGE / Human Body in Space: <https://www.nasa.gov/humans-in-space/the-human-body-in-space/>
- DONKI API: <https://ccmc.gsfc.nasa.gov/DONKI/api/>
- NASA radiation protection brief (600 mSv, 250 mSv, ~0.5 mSv/day): <https://www.nasa.gov/wp-content/uploads/2023/03/radiation-protection-technical-brief-ochmo.pdf>
- NASA CO2 brief (3 mmHg 1-h; 2.5 mmHg 7-day): <https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-004-carbon-dioxide.pdf> and <https://nasa.gov/wp-content/uploads/2023/03/co2-technical-brief-ochmo.pdf>
- NASA ECLSS brief (18–27 °C): <https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-002-eclss.pdf>
- CSA Radi-N2 (neutrons ~30%, ~150 µSv/day): <https://www.asc-csa.gc.ca/eng/sciences/radi-n2.asp>
- CSA Space Health / Bio-Monitor (cardiovascular): <https://hdiac.dtic.mil/articles/peak-performance-in-microgravity>
- Three-Item Loneliness Scale: <https://www.phenxtoolkit.org/toolkit_content/supplemental_info/psychosocial/measures/Social_Isolation.doc>
- PVT-B validation (355 ms lapse): <https://pmc.ncbi.nlm.nih.gov/articles/PMC3197786>
- 3-min PVT lapse bands (11 / 20): <https://pmc.ncbi.nlm.nih.gov/articles/PMC3190077>
- Subjective vs objective gap (NASA JSC, Basner): <https://www.24-7pressrelease.com/press-release/414258/clearing-the-space-fog>
- AURORA (main rival): <https://github.com/fabriciojunio/aurora-astronaut-health>

# Backend update: what changed, and the extra APIs you can use

**For the frontend team.** The backend is now **one system**: one crew (Hashir, Ahmad, Hannan, Sabaina), one clock
(mission hours), one analysis engine and one database. Everything is in the shape the frontend uses (camelCase JSON,
mission hours, `nominal | watch | alert`).

1. **All 29 endpoints of the Nova Healix API v2 guide are implemented** (section 1, short).
2. **Four extra features are on the same core** (section 2, with details): the **Mobility & Balance Check**, **ECHO**
   (the scored isolation check-in chat), **distance**, and a one-call **dashboard** with **alerts**.
   Each one feeds the screens you already have (Isolation and Gravity hazards, findings), so they need little or no
   frontend work. **Please use them** (section 3).

> Decision support prototype, not a medical device. Crew data is simulated. Space weather (NASA DONKI) and distance
> (NASA JPL Horizons) can be real NASA data.

Railway: `https://nova-healix-backend-production.up.railway.app` · Swagger: `/docs` · Local: `http://127.0.0.1:8000`.
Crew ids: `hashir`, `ahmad`, `hannan`, `sabaina`. Status words everywhere: `nominal | watch | alert`.

---

## 1. Nova Healix API v2: done (follows the frontend guide)

| Area | Endpoints |
|---|---|
| Mission | `GET /api/mission`, `/api/mission/events`, `/api/crew/{id}/timeline?from&to` |
| Crew | `GET /api/crew`, `/api/crew/{id}` |
| Telemetry | `GET /api/crew/{id}/metrics/{metric}?from&to&bucket`, `…/baseline`, `/vitals/live`, `/checkins?from&to` |
| Assessment | `GET /api/assessment/hazards`, `…/hazards/{hazard}/history?crew&fromDay`, `…/crew-summaries`, `GET /api/insights`, `GET /api/crew/{id}/metrics/{metric}/interpretation` (all take `at`, `autonomous`) |
| Crew Mode | `POST /api/crew/{id}/checkins`, `GET /api/questionnaires`, `GET /api/crew/{id}/assignments`, `GET /api/assignments/{id}`, `PUT …/progress`, `POST …/submit` |
| Nova | `POST /api/crew/{id}/companion/reply`, `POST /api/crew/{id}/shared-notes` |
| Mission Control | `GET/POST /api/actions`, `GET/POST /api/crew/{id}/messages`, `POST /api/insights/{id}/resolve`, `…/reopen` |

- **Verified**: the analysis engine matches the frontend's own engine exactly (scores, drivers, insights, Nova replies;
  `tests/test_parity.py`). The real frontend (`?data=api`) runs against it with no console errors.
- **Nova is private**: stateless; nothing is stored, logged or scored. The only exception is the safety exception
  (a content-free alert for Mission Control).
- **Small differences from the guide** (deliberate):
  - The guide's check-in draft example shows `energy: 3`; the frontend's engine returns `2`, so we match the engine.
  - Real NASA storm events are added to `GET /api/mission/events` (`source: "NASA DONKI"`) but do not change dose numbers.
  - `GET /api/mission` also returns `trajectorySource` (`"NASA JPL Horizons"` when the arrival distance is real NASA data).
  - 422 bodies are `{"detail": "field: message"}` and never echo what was sent. Questionnaire scale answers must be 1 to 5.
  - `GET /health` → `{status, version, companion, echo, database, missionHour}`.

---

## 2. Extra features (not in the guide), all on the same core

### 2.1 Mobility & Balance Check

Three short movement tests (about 2 minutes): single-leg balance, 5x sit-to-stand, squat knee bend.
**MediaPipe Pose runs in the browser** (live skeleton and measurements); the server only receives five numbers and
scores them. No video leaves the device, no YOLO. It measures movement only, **not bone health**.

**No change to existing screens needed**: a check shows up by itself as a **Gravity driver** "Mobility & balance check"
in `GET /api/assessment/hazards` (no `metric`, nothing to special-case) and as a **finding** `mobility:<crewId>`
(watch or alert, `primaryMetric: "legStrength"`) in `GET /api/insights`.

`GET /api/mobility/method`: the tests, what to send, thresholds, `minPoseConfidence` (0.6), the limits text.

`POST /api/mobility/{crewId}` (201):
```json
{ "balanceHoldS": 22, "swayPctHeight": 1.4, "sitToStandS": 10.8, "kneeFlexionDeg": 112, "poseConfidence": 0.91 }
```
| Field | Range | Meaning |
|---|---|---|
| `balanceHoldS` | 0 to 30 | seconds on one leg (stop at 30) |
| `swayPctHeight` | 0 to 50 | RMS sway of the hip centre, % of body height |
| `sitToStandS` | above 1, up to 120 | seconds for 5 sit-to-stands |
| `kneeFlexionDeg` | 0 to 150 | deepest knee bend (above 150 is a tracking error: 422) |
| `poseConfidence` | 0 to 1 | mean keypoint visibility (below 0.6 the check is saved but not used) |

```json
{
  "check": { "id": "mob-ahmad-4fe0d5ea", "crewId": "ahmad", "day": 142, "at": 3394.85, "measurements": { "...": 0 }, "reliable": true },
  "counted": true, "message": "Check saved.",
  "result": {
    "status": "nominal | watch | alert",
    "tests": [ { "test": "balance | sit_to_stand | squat_rom", "label": "Single-leg balance", "status": "watch",
                 "values": { "balanceHoldS": 6, "swayPctHeight": 2.4 },
                 "baseline": { "balanceHoldS": 30, "swayPctHeight": 1 },
                 "changePct": { "balanceHoldS": 80, "swayPctHeight": 140 },
                 "note": "Worse than expected: repeat the test and review." } ],
    "checksUsed": 2, "lastCheckAt": 3394.85, "lastCheckDay": 142 } }
```
`baseline` and `changePct` are `null` on the first check (later checks are compared with the first reliable one).
If `counted` is `false`, `result` is `null`: show `message` and ask for a retake. Errors: 404 unknown crew, 422 bad values.
`GET /api/mobility/{crewId}` → `{ crewId, checks[], latest }` for a history chart.

Cut-offs are illustrative, ours: balance hold under 10 s watch, under 5 s alert; sit-to-stand 12 s / 15 s; squat under
100° / 80°; 25% / 50% worse than the astronaut's own first check.

**Build the page**: a working reference is served at **`/demo/mobility/`** (source `app/static/mobility/index.html`).
Port it into an Angular component with `@mediapipe/tasks-vision` (`PoseLandmarker`, video mode, lite model):
- Landmarks used: nose, shoulders (11, 12), hips (23, 24), knees (25, 26), ankles (27, 28). Work in **pixels**.
- Knee bend = 180 minus the hip-knee-ankle angle on the better-seen leg; **ignore frames above 150°**.
- Balance: foot lifted when the ankle height gap exceeds 8% of body height (nose to mid-ankle) for 0.3 s; hold ends on
  touch-down (over 0.5 s) or 30 s; sway = RMS of the hip-centre around its mean, % of body height.
- Sit-to-stand (start seated): leave seat at bend below 45°, stand below 25°, sit again above 55°; time to the 5th stand.
- Squat: a rep is bend above 50° then below 25°; `kneeFlexionDeg` = median of 3 peaks. `poseConfidence` = mean
  visibility of hips, knees, ankles.
- **Side-on to the camera, whole body in view**; show a "turn side-on / step back" hint when tracking is poor.
- Host the WASM files and `pose_landmarker_lite.task` in `assets/` to work offline. Try `delegate: "GPU"`, fall back
  to `"CPU"`. The camera needs https or `localhost`.
- Keep visible: "Decision-support prototype, not a medical device. Measures movement, not bone health. Video stays on this device."

### 2.2 ECHO: the scored isolation check-in chat (Ahmed's work)

A Gemini-powered chat that **scores** loneliness (Three-Item Loneliness Scale, 3 to 9). Unlike Nova it is **stored**
(transcript and score), so use it where a measured, auditable check-in is wanted, and Nova where privacy matters.
It uses the same crew and today's mission day.

| Call | Purpose |
|---|---|
| `GET /api/isolation/method` | instrument, items, 1-3 scale, `minTurns` 3, `maxTurns` 10, `bands` (nominal 3-5, watch 6+, alert 7+ for 3 days in a row or a safety concern) |
| `POST /api/isolation/{crewId}/sessions` (201) | start → `{session, messages:[opening message], minTurns, maxTurns}` |
| `POST …/sessions/{sid}/messages` | body `{"content": "text"}` → `{sessionId, reply, astronautTurns, canComplete, mustComplete}` |
| `POST …/sessions/{sid}/complete` | score it (idempotent) → `{id, sessionId, crewId, missionDay, at, q1, q2, q3, score, confidence, reliable, safetyConcern, status, consecutiveHighDays, rationale, evidence[], what, why, action, source, model, createdAt}` |
| `GET …/sessions/{sid}` | `{session, messages, assessment}` |
| `GET /api/isolation/{crewId}` | `{crewId, items:[{day, score, status, confidence, reliable, sessionId}]}` |

Flow: start, send 3 to 10 replies, call `/complete` once `canComplete` is true (required when `mustComplete`).
Errors: 404 unknown crew/session, 409 closed session, reply limit or too few replies, 422 empty message,
**503 when `GEMINI_API_KEY` is not set or Gemini is unavailable** (nothing else is affected; `GET /health` shows `echo`).

**It feeds the Isolation hazard by itself**: a scored check-in adds the driver "Loneliness, ECHO check-in" (value
`7/9`, no `metric`) to `GET /api/assessment/hazards`, and an elevated or safety-flagged one raises a finding
`loneliness:<crewId>` (watch or alert) in `GET /api/insights`. A low-confidence rating is stored but ignored, except that
a safety concern is always shown.

### 2.3 Distance from Earth (Ahmed's work)

`GET /api/distance` → `{ mission:"mars", target:"Mars", source, asOf, durationDays:260, days:[{day, distanceKm, lightTimeS}] }`.
Earth-ship distance and one-way signal delay at the start of every mission day, from the same trajectory that sets the
signal delay everywhere else. `source` is `"NASA JPL Horizons"` when the Mars arrival distance is real NASA data
(`asOf` says when it was fetched), else `"model"`. Good for a distance / delay chart.

### 2.4 Dashboard and alerts

- `GET /api/dashboard?at&autonomous` → one call for an overview screen:
  `{disclaimer, missionHour, day, durationDays, link:{mode, delaySeconds, distanceAu}, recentSpaceEvents[] (real NASA
  events in the last 24 h), crew:[{astronaut, summary, hazards[5], insights[] (active)}], crewWideInsights[]}`.
- `GET /api/alerts?at&autonomous` → active (unresolved) findings at `watch` or `alert` severity, most urgent first
  (`Insight[]`, the same shape as `/api/insights`).

---

## 3. Frontend team: please use these

1. **Build the Mobility & Balance Check page** (2.1). It is the only feature with no screen yet; it costs one component
   and one POST, and the Gravity hazard and findings you already show pick it up.
2. **Offer ECHO** (2.2) next to the private Nova chat where a scored check-in is useful. Its results appear in the
   Isolation hazard and findings with no extra work.
3. **Use `GET /api/distance`** (2.3) for a real distance and signal-delay chart.
4. **Use `GET /api/dashboard`** (2.4) if a simple overview screen should load in one request.
5. Read `trajectorySource` and the `source` on mission events if you want to label what is real NASA data.

Tell us which of these you will use and any field you want changed; the backend can adapt the shapes.

## 4. Setup (backend)

- Env (`.env.example`): `NASA_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `CORS_ORIGINS` (add the deployed
  frontend), optional `GEMINI_API_KEY` (ECHO, and Nova's open-ended replies).
- **One database**: run `supabase/schema.sql` once. If the project still has the old RIDGE tables, `supabase/cleanup_old_tables.sql`
  removes them (optional, it deletes their data).
- `make run` → `/docs`; `make check` (ruff, strict mypy, 215 tests). Per-item status: [V2_TRACKER.md](V2_TRACKER.md).
- Frontend against it: in `Nova-Helix` run `npm start`, open `http://localhost:4200/?data=api`.

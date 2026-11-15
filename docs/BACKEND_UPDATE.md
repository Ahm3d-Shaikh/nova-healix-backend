# Backend update: what changed, and the extra APIs you can use

**For the frontend team.** One service, two sets of endpoints:

1. **Everything in the Nova Healix API v2 guide is implemented** (all 29 endpoints). Section 1, short.
2. **Nothing else was removed.** Our own endpoints (Mobility & Balance Check) and Ahmed's (ECHO check-in chat,
   distance, RIDGE dashboard and alerts) are all still here, running next to v2. Section 2, with details.
   **Please use them** (section 3).

> Decision support prototype, not a medical device. Crew data is simulated. Space weather (NASA DONKI) and distance
> (NASA JPL Horizons) can be real NASA data.

Base URL (Railway): `https://nova-healix-backend-production.up.railway.app` · Swagger: `/docs` ·
Local: `http://127.0.0.1:8000`. All times in v2 are **mission hours** (float); camelCase JSON. The RIDGE endpoints
(ECHO, distance, dashboard) keep their original **snake_case** and mission **days**.

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

- **Verified**: the analysis engine matches the frontend's own engine exactly (scores, drivers, insights, Nova
  replies; `tests/test_parity.py`). The real frontend (`?data=api`) runs against it: Mission Control, profile, Nova,
  check-in, resolve, no console errors.
- **Nova is private**: the reply endpoint is stateless; nothing is stored, logged or scored. The only exception is the
  safety exception (a content-free alert for Mission Control).
- **Small differences from the guide** (all deliberate):
  - The check-in draft example in the guide shows `energy: 3`; the frontend's engine returns `2`, so we match the engine.
  - Real NASA storm events are added to `GET /api/mission/events` (`source: "NASA DONKI"`) but do not change dose numbers
    (that keeps us identical to the frontend's demo data).
  - `GET /api/mission` also returns `trajectorySource` (`"NASA JPL Horizons"` when the Mars arrival distance is live NASA data).
  - 422 bodies are `{"detail": "field: message"}` and never echo what was sent. Questionnaire scale answers must be 1 to 5.
  - `GET /health` returns `{status, version, companion, missionHour, database, ai_checkin}`.
- **Two paths moved** because v2 needs them: the old RIDGE `GET /api/crew` and `GET /api/crew/{id}` are now
  `GET /api/ridge/crew` and `GET /api/ridge/crew/{id}`; the old RIDGE mobility is `/api/ridge/mobility/*`.

---

## 2. Extra APIs (not in the guide, all working)

### 2.1 Mobility & Balance Check (our addition)

Three short movement tests (about 2 minutes): single-leg balance, 5x sit-to-stand, squat knee bend.
**MediaPipe Pose runs in the browser** (live skeleton and measurements); the server only receives five numbers and
scores them. No video leaves the device, no YOLO. It measures movement only, **not bone health**.

**It needs no changes to existing screens**: once a check exists it appears by itself as
a **Gravity driver** "Mobility & balance check" in `GET /api/assessment/hazards` (no `metric`, so nothing to special-case),
and as a **finding** `mobility:<crewId>` (watch or alert, `primaryMetric: "legStrength"`) in `GET /api/insights`.
It resolves, reopens and logs like any other finding.

`GET /api/mobility/method`: the tests, what to send, thresholds, `minPoseConfidence` (0.6), the limits text.

`POST /api/mobility/{crewId}` (201), crewId is `hashir|ahmad|hannan|sabaina`:
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

`GET /api/mobility/{crewId}` → `{ crewId, checks[], latest }` (for a history chart).

Cut-offs are illustrative, ours: balance hold under 10 s watch, under 5 s alert; sit-to-stand 12 s / 15 s; squat under
100° / 80°; 25% / 50% worse than the astronaut's own first check.

**Build the page**: a working reference is served at **`/demo/mobility/`** (source `app/static/mobility/index.html`).
Port it into an Angular component with `@mediapipe/tasks-vision` (`PoseLandmarker`, video mode, lite model):
- Landmarks used: nose, shoulders (11, 12), hips (23, 24), knees (25, 26), ankles (27, 28). Work in **pixels**.
- Knee bend = 180 minus the hip-knee-ankle angle on the better-seen leg; **ignore frames above 150°**.
- Balance: foot lifted when the ankle height gap exceeds 8% of body height (nose to mid-ankle) for 0.3 s; hold ends on
  touch-down (over 0.5 s) or 30 s; sway = RMS of the hip-centre around its mean, % of body height.
- Sit-to-stand (start seated): leave seat at bend below 45°, stand below 25°, sit again above 55°; time to the 5th stand.
- Squat: a rep is bend above 50° then below 25°; `kneeFlexionDeg` = median of 3 peaks. `poseConfidence` = mean visibility
  of hips, knees, ankles.
- **Side-on to the camera, whole body in view**; show a "turn side-on / step back" hint when tracking is poor.
- Host the WASM files and `pose_landmarker_lite.task` in `assets/` to work offline (the page loads them from a CDN).
  Try `delegate: "GPU"`, fall back to `"CPU"`. Camera needs https or `localhost`.
- Keep visible: "Decision-support prototype, not a medical device. Measures movement, not bone health. Video stays on this device."

### 2.2 ECHO isolation check-in chat (Ahmed's work)

A Gemini-powered chat that **scores** loneliness (Three-Item Loneliness Scale, 3 to 9). It uses the RIDGE crew
(`A`, `B`, `C`) and mission **days** (`?day=`, 1 to 30). Unlike Nova it is stored and scored, so use it where a
measured, auditable check-in is wanted, and Nova where privacy matters.

| Call | Purpose |
|---|---|
| `GET /api/isolation/method` | instrument, items, 1-3 scale, `min_turns` 3, `max_turns` 10, bands (green 3-5, amber 6+, red 7+ for 3 days or a safety concern) |
| `POST /api/isolation/{id}/sessions?day=` (201) | start the chat → `{session, messages:[opening message], min_turns, max_turns}` |
| `POST /api/isolation/{id}/sessions/{sid}/messages` | body `{"content": "text"}` → `{session_id, reply, astronaut_turns, can_complete, must_complete}` |
| `POST /api/isolation/{id}/sessions/{sid}/complete` | score it (idempotent) → `{q1,q2,q3,score,confidence,reliable,safety_concern,level,consecutive_days_at_or_above_7,rationale,evidence[],alert{what,why,action,source},model,...}` |
| `GET /api/isolation/{id}/sessions/{sid}` | transcript and assessment |
| `GET /api/isolation/{id}` | `{astronaut_id, items:[{day, source:"simulated"|"ai_checkin", score, level, confidence, reliable, session_id}]}` (score per day) |

Flow: start, send 3 to 10 replies, call `/complete` once `can_complete` is true (required when `must_complete`). Errors:
404 unknown id/session, 409 closed session or reply limit, 422 empty message, **503 when `GEMINI_API_KEY` is not set**
(the rest of the app still works). Reliable check-ins also replace that day's simulated score on the RIDGE Isolation card.

### 2.3 Distance from Earth (Ahmed's work)

`GET /api/distance` → `{ mission, target_name, source, data_as_of, reason, days:[{day, distance_km, light_time_s}] }`.
Real JPL Horizons distance and one-way light time for each mission day (`source` is `live`, `cached` or `snapshot`,
with `reason` when not live). Good for a distance / signal-delay chart. (v2's `trajectoryAu` in `/api/mission` is the
simulated 260-day transfer; this endpoint is the real geocentric ephemeris for the RIDGE 30-day mission.)

### 2.4 RIDGE dashboard, alerts and crew (the earlier 3-astronaut app)

| Call | Returns |
|---|---|
| `GET /api/dashboard?day=N` | everything for one screen: settings, data-source status, space-weather events in the last 24 h, per astronaut six cards (R, I, D, G, E, MIRROR) with level, headline and typed `metrics`, plus the alert list |
| `GET /api/alerts?day=N` | all amber/red alerts across the crew, worst first |
| `GET /api/ridge/crew?day=N` | astronauts with overall and per-card level |
| `GET /api/ridge/crew/{id}?day=N` | one astronaut: records up to day N, cards, alerts, Mirror Gap series |

Day `N` is 1 to 30 (422 otherwise). Cards use levels `green|amber|red`; v2 uses `nominal|watch|alert`.
Details for every field: [ridge/FRONTEND_API_GUIDE.md](ridge/FRONTEND_API_GUIDE.md).

---

## 3. Frontend team: please use these

1. **Build the Mobility & Balance Check page** (section 2.1). It is the only new feature with no screen yet; it feeds
   the Gravity hazard and findings you already show, so it costs one component and one POST.
2. **Use `GET /api/distance`** for a real distance and signal-delay chart (section 2.3).
3. **Offer ECHO** where a scored isolation check-in is useful (section 2.2), next to the private Nova chat. If you
   want it, we can also expose its result as a v2 finding.
4. **Use `GET /api/dashboard`** if you want a single-call overview for a simple screen (section 2.4).
5. Read `trajectorySource` and the `source` on mission events if you want to label what is real NASA data.

Tell us which of these you will use and any field you need changed; the backend can adapt the shapes.

## 4. Setup and checks (backend)

- Env (`.env.example`): `NASA_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `CORS_ORIGINS` (add the deployed
  frontend), optional `GEMINI_API_KEY` (ECHO and Nova's open-ended replies).
- Run `supabase/schema.sql` once in Supabase. It keeps the RIDGE tables and adds the v2 ones (nothing is dropped).
- `make run` → `/docs`; `make check` (ruff, strict mypy, 287 tests). Per-item status: [V2_TRACKER.md](V2_TRACKER.md).
- Frontend against it: in `Nova-Helix` run `npm start`, open `http://localhost:4200/?data=api`.

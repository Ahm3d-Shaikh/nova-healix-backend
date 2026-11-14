# RIDGE Monitor API: Frontend Integration Guide

This guide covers every endpoint the frontend uses, with request and response examples, TypeScript
types, and a step-by-step guide to building the Gemini check-in chatbot (ECHO).

> **Decision support prototype, not a medical device.** Crew vitals are simulated. Space weather (NASA DONKI)
> and distance (NASA JPL Horizons) are real NASA data.

## Contents

1. [Basics](#1-basics)
2. [Endpoint summary](#2-endpoint-summary)
3. [Shared types](#3-shared-types)
4. [Astronauts](#4-astronauts)
5. [Alerts](#5-alerts)
6. [Dashboard](#6-dashboard)
7. [Distance](#7-distance)
8. [Chatbot (ECHO check-in)](#8-chatbot-echo-check-in)
9. [Building the Gemini chatbot in the frontend](#9-building-the-gemini-chatbot-in-the-frontend)
10. [Errors](#10-errors)
11. [Mobility & Balance Check](#11-mobility--balance-check)

---

## 1. Basics

| | |
|---|---|
| Local base URL | `http://127.0.0.1:8000` |
| Production base URL | `https://nova-healix-backend-production.up.railway.app` |
| Interactive docs | `{base}/docs` (Swagger UI): try any endpoint in the browser |
| Format | JSON in, JSON out. Timestamps are ISO 8601 UTC (`2026-11-14T17:38:26.570026Z`). |
| Auth | None. |
| CORS | Only origins listed in the backend's `CORS_ORIGINS` env var are allowed (default `http://localhost:4200`). Ask the backend team to add your deployed frontend URL. |
| Methods / headers | `GET` and `POST`, with `Content-Type: application/json`. |

**Mission day.** The mission is 30 days long (days 1–30). Most endpoints take an optional `?day=N`.
If you leave it out, the backend uses the saved "current day" (default **5**). Use `?day=` to drive a day slider.

**Mission settings.** The mission (`iss` / `moon` / `mars`), the current day and deep-space mode live in the
`mission_settings` table in Supabase. There is no API to change them; the dashboard response shows the
current values in `settings`.

**Levels.** Every status is `"green"`, `"amber"` or `"red"` (red = worst).

**Hazards (cards).** Each astronaut has six cards:

| `hazard` | Label | What it shows |
|---|---|---|
| `R` | Radiation | Solar storm events (DONKI) + dose vs NASA limits |
| `I` | Isolation & confinement | Loneliness score from the ECHO chatbot (simulated before any chat) |
| `D` | Distance from Earth | Real distance + signal delay (JPL Horizons), data freshness |
| `G` | Gravity fields | Heart rate / blood pressure drift, missed exercise |
| `E` | Hostile / closed environments | Cabin CO2 and temperature |
| `MIRROR` | Mirror Gap | Self-rated sharpness vs reaction-test performance |

**Response headers.** Every response has `X-Request-ID` (quote it in bug reports) and `X-Process-Time-Ms`.

---

## 2. Endpoint summary

| Area | Method | Path | Purpose |
|---|---|---|---|
| Astronauts | GET | `/api/crew?day=` | All astronauts with overall + per-card level |
| Astronauts | GET | `/api/crew/{astronautId}?day=` | One astronaut: cards with metrics, alerts, daily records |
| Alerts | GET | `/api/alerts?day=` | All amber/red alerts across the crew, worst first |
| Dashboard | GET | `/api/dashboard?day=` | Everything for the main screen in one call |
| Distance | GET | `/api/distance` | Earth distance + signal delay for every mission day |
| Chatbot | GET | `/api/isolation/method` | How chats are scored (for an info panel) |
| Chatbot | POST | `/api/isolation/{astronautId}/sessions?day=` | Start a check-in chat |
| Chatbot | POST | `/api/isolation/{astronautId}/sessions/{sessionId}/messages` | Send the astronaut's message, get ECHO's reply |
| Chatbot | POST | `/api/isolation/{astronautId}/sessions/{sessionId}/complete` | Finish the chat and get the loneliness score |
| Chatbot | GET | `/api/isolation/{astronautId}/sessions/{sessionId}` | Transcript + score of one chat |
| Chatbot | GET | `/api/isolation/{astronautId}` | Loneliness score history |
| Mobility | GET | `/api/mobility/method` | The 3 tests, what to send, thresholds, limits |
| Mobility | POST | `/api/mobility/{astronautId}?day=` | Save a check measured in the browser (feeds the Gravity card) |
| Mobility | GET | `/api/mobility/{astronautId}` | Check history + latest result |
| Ops | GET | `/health` | Liveness + whether the chatbot is enabled |

Astronaut ids are `"A"`, `"B"`, `"C"` (case-insensitive).

---

## 3. Shared types

Copy these into the frontend (for example `src/app/api/ridge.models.ts`).

```ts
export type Level = 'green' | 'amber' | 'red';
export type Hazard = 'R' | 'I' | 'D' | 'G' | 'E' | 'MIRROR';
export type DataSource = 'live' | 'cached' | 'snapshot';
export type Mission = 'iss' | 'moon' | 'mars';

export interface Astronaut {
  id: string;          // "A" | "B" | "C"
  name: string;        // display name (editable in Supabase)
  role: string;        // "Commander", ...
  story: string;       // demo storyline
}

/** One rule result. Green results are included in cards; only amber/red appear in alert lists. */
export interface Alert {
  rule: string;        // e.g. "R.sep_24h", "I.loneliness", "D.comms_delay"
  hazard: Hazard;
  level: Level;
  what: string;        // what was observed (show as the main text)
  why: string;         // why it matters
  action: string;      // what to do
  source: string;      // data / method source (show small)
}

export interface CrewAlert extends Alert {
  astronaut_id: string;
  astronaut_name: string;
  day: number;
}

export interface CardStatus {
  hazard: Hazard;
  label: string;
  level: Level;                // worst level of the card's alerts
  headline: string;            // plain-text summary (the worst alert's `what`): show it so status is never colour-only
  alerts: Alert[];             // every rule result for this card (green included)
  metrics: CardMetrics;        // numbers for gauges/charts; switch on metrics.kind
}

export type CardMetrics =
  | RadiationMetrics | IsolationMetrics | DistanceMetrics
  | GravityMetrics | EnvironmentMetrics | MirrorMetrics;

export interface RadiationMetrics {
  kind: 'radiation';
  cumulative_dose_msv: number;
  career_limit_msv: number;        // 600
  percent_of_limit: number;        // 0-100
  latest_daily_dose_msv: number;
  neutron_share_estimate: number;  // 0.3
  neutron_dose_estimate_msv: number;
  iss_neutron_usv_per_day: number;
  sep_events_24h: number;
  x_flares_24h: number;
  cmes_24h: number;
  data_source: DataSource;
  data_as_of: string;
}

export interface IsolationMetrics {
  kind: 'isolation';
  loneliness_score: number;        // 3-9 for the selected day
  scale_min: number;               // 3
  scale_max: number;               // 9
  amber_threshold: number;         // 6
  red_threshold: number;           // 7
  red_consecutive_days: number;    // 3
  consecutive_days_at_or_above_7: number;
  trend: 'rising' | 'falling' | 'stable' | 'insufficient_data';  // last 3 days vs the 3 before
  trend_delta: number | null;      // change in average score (+ = lonelier)
  latest_source: 'simulated' | 'ai_checkin';  // did today's score come from an ECHO chat?
  safety_concern: boolean;         // ECHO flagged a wellbeing concern today
  ai_checkin_days: number[];       // days scored by ECHO
  history: number[];               // score per day, day 1..selected day
}

export interface DistanceMetrics {
  kind: 'distance';
  mission: Mission;
  comms_delay: string;             // human readable, e.g. "16 min 09 s"
  deep_space_mode: boolean;
  data_source: DataSource;         // space-weather feed status
  data_as_of: string;
  target_name: string | null;      // "International Space Station" | "Moon" | "Mars"
  distance_km: number | null;
  distance_au: number | null;
  one_way_light_time_s: number | null;
  round_trip_light_time_s: number | null;
  range_rate_km_s: number | null;  // + moving away, - approaching
  distance_source: DataSource | null;
  distance_as_of: string | null;
}

export interface Vital {
  value: number;
  baseline_mean: number | null;
  threshold: number | null;        // baseline mean + 2 SD
  above_threshold: boolean | null;
}

export interface GravityMetrics {
  kind: 'gravity';
  baseline_ready: boolean;         // false for days 1-7
  resting_hr: Vital;
  sys_bp: Vital;
  dia_bp: Vital;
  exercise_min: number;
  exercise_missed_days: number;
  drifting: string[];              // e.g. ["resting HR"]
}

export interface EnvironmentMetrics {
  kind: 'environment';
  co2_mmhg_1h: number;  co2_1h_limit: number;
  co2_mmhg_7d: number;  co2_7d_limit: number;
  cabin_temp_c: number; temp_min_c: number; temp_max_c: number;
}

export interface MirrorMetrics {
  kind: 'mirror';
  gap: number | null;              // null during the first 5 days (baseline)
  amber_gap: number;
  red_gap: number;
  self_rating: number;             // 1-10
  pvt_mean_rt_ms: number;
  pvt_lapses: number;
  lapse_band: 'good' | 'reduced' | 'poor';
  baseline_sessions: number;
}
```

---

## 4. Astronauts

### GET `/api/crew`

List of astronauts with their overall level and one level per card. Use it for the crew overview / sidebar.

| Query | Type | Required | Notes |
|---|---|---|---|
| `day` | int 1–30 | no | defaults to the saved current day |

```http
GET /api/crew?day=20
```

**200 response:** `AstronautSummary[]`

```json
[
  {
    "astronaut": {
      "id": "A",
      "name": "Astronaut A",
      "role": "Commander",
      "story": "Healthy reference: normal noise around a stable baseline."
    },
    "day": 20,
    "overall": "red",
    "cards": { "R": "red", "I": "green", "D": "amber", "G": "green", "E": "green", "MIRROR": "green" }
  }
]
```

```ts
export interface AstronautSummary {
  astronaut: Astronaut;
  day: number;
  overall: Level;
  cards: Record<Hazard, Level>;
}
```

### GET `/api/crew/{astronautId}`

Full detail for one astronaut: six cards with metrics, the amber/red alerts, raw daily records (for charts)
and the Mirror Gap series.

```http
GET /api/crew/C?day=25
```

**200 response:** `CrewDetail` (shortened: one card and one record shown)

```json
{
  "astronaut": { "id": "C", "name": "Astronaut C", "role": "Mission Specialist", "story": "From day 10: resting HR drifts up, exercise skipped, loneliness score rises." },
  "day": 25,
  "overall": "red",
  "cards": [
    {
      "hazard": "G",
      "label": "Gravity fields",
      "level": "red",
      "headline": "Readings flagged for review: resting HR above baseline + 2 SD for ≥3 days; exercise missed 2+ consecutive days.",
      "alerts": [
        {
          "rule": "G.cardio",
          "hazard": "G",
          "level": "red",
          "what": "Readings flagged for review: resting HR above baseline + 2 SD for ≥3 days; exercise missed 2+ consecutive days.",
          "why": "Cardiovascular deconditioning is a known effect of altered gravity.",
          "action": "Flag for review by flight surgeon; resume exercise protocol today.",
          "source": "Baseline = days 1-7 mean ± SD per astronaut; thresholds illustrative (CSA Bio-Monitor style monitoring)"
        }
      ],
      "metrics": {
        "kind": "gravity",
        "baseline_ready": true,
        "resting_hr": { "value": 70.9, "baseline_mean": 61.64, "threshold": 64.64, "above_threshold": true },
        "sys_bp": { "value": 120.6, "baseline_mean": 117.3, "threshold": 123.3, "above_threshold": false },
        "dia_bp": { "value": 79.1, "baseline_mean": 76.19, "threshold": 80.19, "above_threshold": false },
        "exercise_min": 0.0,
        "exercise_missed_days": 16,
        "drifting": ["resting HR"]
      }
    }
  ],
  "alerts": [ { "rule": "I.loneliness", "hazard": "I", "level": "red", "what": "Loneliness score 8/9; ≥7 for 11 consecutive days.", "why": "...", "action": "...", "source": "..." } ],
  "records": [
    {
      "day": 25,
      "sleep_hours": 6.9, "resting_hr": 70.9, "sys_bp": 120.6, "dia_bp": 79.1, "exercise_min": 0.0,
      "co2_mmhg_1h": 2.28, "co2_mmhg_7d": 1.87, "cabin_temp_c": 22.0,
      "loneliness_q1": 3, "loneliness_q2": 3, "loneliness_q3": 2, "loneliness_total": 8,
      "self_rating": 7, "pvt_mean_rt": 283.3, "pvt_mean_speed": 3.53, "pvt_lapses": 4, "pvt_false_starts": 1,
      "dose_msv": 0.45,
      "loneliness_source": "simulated",
      "isolation_safety_flag": false
    }
  ],
  "mirror_gap_series": [ { "day": 24, "gap": 0.21 }, { "day": 25, "gap": 0.137 } ],
  "radiation_source": "snapshot"
}
```

```ts
export interface DailyRecord {
  day: number;
  sleep_hours: number; resting_hr: number; sys_bp: number; dia_bp: number; exercise_min: number;
  co2_mmhg_1h: number; co2_mmhg_7d: number; cabin_temp_c: number;
  loneliness_q1: number; loneliness_q2: number; loneliness_q3: number; loneliness_total: number;
  self_rating: number; pvt_mean_rt: number; pvt_mean_speed: number; pvt_lapses: number; pvt_false_starts: number;
  dose_msv: number;
  loneliness_source: 'simulated' | 'ai_checkin';
  isolation_safety_flag: boolean;
}

export interface CrewDetail {
  astronaut: Astronaut;
  day: number;
  overall: Level;
  cards: CardStatus[];             // always 6, in order R, I, D, G, E, MIRROR
  alerts: Alert[];                 // amber/red only, worst first
  records: DailyRecord[];          // days 1..day (use for line charts)
  mirror_gap_series: { day: number; gap: number | null }[];
  radiation_source: DataSource;
}
```

**Errors:** `404` unknown astronaut, `422` day outside 1–30.

---

## 5. Alerts

### GET `/api/alerts`

Every amber and red alert across the whole crew, **worst first** (red before amber, then by astronaut id).
Use it for the alert panel or a notification badge (`alerts.length`).

```http
GET /api/alerts?day=20
```

**200 response:** `CrewAlert[]`

```json
[
  {
    "rule": "R.sep_24h",
    "hazard": "R",
    "level": "red",
    "what": "2 SEP detection(s) in the last 24 h (latest 2024-05-09 14:25 UTC).",
    "why": "Energetic solar particles penetrate hull and tissue and can deliver a large dose in hours.",
    "action": "Move to shielded area.",
    "source": "NASA DONKI; event-to-level mapping is ours (illustrative)",
    "astronaut_id": "A",
    "astronaut_name": "Astronaut A",
    "day": 20
  },
  {
    "rule": "D.comms_delay",
    "hazard": "D",
    "level": "amber",
    "what": "Mars: 290,636,747 km from Earth (1.94 AU); one-way signal delay 16 min 09 s (round trip 32 min 19 s).",
    "why": "With a delay this long, Mission Control cannot guide a medical event in real time.",
    "action": "Treat medical issues with onboard protocols first; send Mission Control a written summary.",
    "source": "NASA JPL Horizons ephemeris (one-way light time); alert cut-off is ours (illustrative)",
    "astronaut_id": "A",
    "astronaut_name": "Astronaut A",
    "day": 20
  }
]
```

**Display tip:** show `what` as the headline, `action` as the call to action, and `why` / `source` in an
expandable detail. Group by `astronaut_id` or `hazard` as your design needs. An empty array means all clear.

**Errors:** `422` day outside 1–30.

---

## 6. Dashboard

### GET `/api/dashboard`

**One call for the whole main screen**: mission settings, NASA data status, every astronaut's six cards
(level + metrics + rule results) and the crew alert panel. Prefer this over calling `/api/crew` and
`/api/alerts` separately.

```http
GET /api/dashboard?day=20
```

**200 response:** `DashboardResponse` (shortened: one astronaut, one card)

```json
{
  "disclaimer": "Decision support prototype, not a medical device. Crew data is simulated; space-weather and distance data are real NASA data.",
  "day": 20,
  "mission_days": 30,
  "settings": {
    "mission": "mars",
    "deep_space_mode": false,
    "current_day": 5,
    "comms_delay": "3–22 min",
    "mission_days": 30
  },
  "space_weather": {
    "source": "live",
    "data_as_of": "2026-11-14T08:51:00Z",
    "reason": null,
    "events_last_24h": [
      {
        "id": "2024-05-09T13:59:00-SEP-001",
        "kind": "sep",
        "time": "2024-05-09T13:59:00Z",
        "summary": "Solar energetic particle event (MODEL: REleASE:ACE/EPAM 15.8-39.8 MeV)",
        "class_type": null,
        "speed_km_s": null,
        "kp_index": null,
        "link": "https://ccmc.gsfc.nasa.gov/DONKI/view/SEP/30609/-1",
        "mission_day": 20
      },
      {
        "id": "20240509-AL-002-FLR",
        "kind": "flare",
        "time": "2024-05-09T12:03:00Z",
        "summary": "X2.2 solar flare (from DONKI notification)",
        "class_type": "X2.2",
        "speed_km_s": null,
        "kp_index": null,
        "link": "https://ccmc.gsfc.nasa.gov/DONKI/view/Alert/30607/1",
        "mission_day": 20
      }
    ]
  },
  "distance": {
    "source": "live",
    "data_as_of": "2026-11-14T11:12:32.847180Z",
    "reason": null,
    "target_name": "Mars"
  },
  "crew": [
    {
      "astronaut": { "id": "A", "name": "Astronaut A", "role": "Commander", "story": "Healthy reference: normal noise around a stable baseline." },
      "overall": "red",
      "cards": [
        {
          "hazard": "D",
          "label": "Distance from Earth",
          "level": "amber",
          "headline": "Mars: 290,636,747 km from Earth (1.94 AU); one-way signal delay 16 min 09 s (round trip 32 min 19 s).",
          "alerts": [
            {
              "rule": "D.comms_delay",
              "hazard": "D",
              "level": "amber",
              "what": "Mars: 290,636,747 km from Earth (1.94 AU); one-way signal delay 16 min 09 s (round trip 32 min 19 s).",
              "why": "With a delay this long, Mission Control cannot guide a medical event in real time.",
              "action": "Treat medical issues with onboard protocols first; send Mission Control a written summary.",
              "source": "NASA JPL Horizons ephemeris (one-way light time); alert cut-off is ours (illustrative)"
            },
            {
              "rule": "D.data_freshness",
              "hazard": "D",
              "level": "green",
              "what": "Live NASA links OK. One-way comms delay: 16 min 09 s.",
              "why": "Distance from Earth limits real-time support and resupply.",
              "action": "No action needed.",
              "source": "NASA DONKI / JPL Horizons feed status from this app"
            }
          ],
          "metrics": {
            "kind": "distance",
            "mission": "mars",
            "comms_delay": "16 min 09 s",
            "deep_space_mode": false,
            "data_source": "live",
            "data_as_of": "2026-11-14T08:51:00+00:00",
            "target_name": "Mars",
            "distance_km": 290636747.5,
            "distance_au": 1.942787,
            "one_way_light_time_s": 969.46,
            "round_trip_light_time_s": 1938.92,
            "range_rate_km_s": -6.5355,
            "distance_source": "live",
            "distance_as_of": "2026-11-14T11:12:32.847180+00:00"
          }
        }
      ],
      "alerts": [ { "rule": "R.sep_24h", "hazard": "R", "level": "red", "what": "...", "why": "...", "action": "...", "source": "..." } ]
    }
  ],
  "alerts": [ { "rule": "R.sep_24h", "level": "red", "astronaut_id": "A", "astronaut_name": "Astronaut A", "day": 20, "hazard": "R", "what": "...", "why": "...", "action": "...", "source": "..." } ]
}
```

```ts
export interface SpaceWeatherEvent {
  id: string;
  kind: 'sep' | 'flare' | 'cme' | 'geostorm';
  time: string;
  summary: string;
  class_type: string | null;   // flare class, e.g. "X2.2"
  speed_km_s: number | null;   // CME speed
  kp_index: number | null;     // geomagnetic storm strength
  link: string | null;         // NASA DONKI page
  mission_day: number;
}

export interface DashboardResponse {
  disclaimer: string;                          // show on screen: "Decision support prototype, not a medical device..."
  day: number;
  mission_days: number;                        // 30, use for the day slider max
  settings: {
    mission: Mission;
    deep_space_mode: boolean;
    current_day: number;                       // saved default day
    comms_delay: string;                       // typical delay for the mission
    mission_days: number;
  };
  space_weather: {
    source: DataSource;
    data_as_of: string;
    reason: string | null;                     // why not live: "live_unavailable" | "rate_limited" | "deep_space_mode"
    events_last_24h: SpaceWeatherEvent[];      // SEP / flare / CME / storm in the 24 h before the selected day ends
  };
  distance: {
    source: DataSource;
    data_as_of: string;
    reason: string | null;
    target_name: string;
  };
  crew: {
    astronaut: Astronaut;
    overall: Level;
    cards: CardStatus[];                       // 6 cards, order R, I, D, G, E, MIRROR
    alerts: Alert[];                           // this astronaut's amber/red alerts
  }[];
  alerts: CrewAlert[];                         // whole crew, worst first (same as /api/alerts)
}
```

**Display tips**

- Show a "data source" badge from `space_weather.source` and `distance.source`: `live` (green dot), `cached` or
  `snapshot` (grey dot, with `data_as_of`). `snapshot` means bundled real NASA data is shown because the live feed
  is down.
- Pick the right gauge by switching on `card.metrics.kind`.
- Show `card.headline` under each card's colour so the status can be read without colour.
- Show `disclaimer` somewhere visible (footer or banner).
- On the Isolation card, show `metrics.trend` as an arrow (rising ↑ / falling ↓ / stable →).
- The demo's real solar storm is on **day 20**: try `?day=20` to see red radiation alerts.
- On the Isolation card, show a small "from ECHO check-in" tag when `metrics.latest_source === 'ai_checkin'`,
  and a prominent banner when `metrics.safety_concern` is true.

**Errors:** `422` day outside 1–30, `503` database unavailable.

---

## 7. Distance

### GET `/api/distance`

Distance from Earth and one-way signal delay at the end of **every** mission day, for the Distance chart.
Data comes from NASA JPL Horizons for the current mission's destination (ISS, Moon or Mars).

```http
GET /api/distance
```

**200 response:** `DistanceResponse` (30 items in `days`, two shown)

```json
{
  "mission": "mars",
  "target_name": "Mars",
  "source": "live",
  "data_as_of": "2026-11-14T11:12:32.847180Z",
  "reason": null,
  "days": [
    { "day": 1, "distance_km": 301344065.5, "light_time_s": 1005.176 },
    { "day": 2, "distance_km": 300778907.2, "light_time_s": 1003.29 }
  ]
}
```

```ts
export interface DistanceResponse {
  mission: Mission;
  target_name: string;
  source: DataSource;
  data_as_of: string;
  reason: string | null;
  days: { day: number; distance_km: number; light_time_s: number }[];  // light_time_s = one-way delay
}
```

**Display tips:** format `light_time_s` as minutes and seconds for Mars (`Math.floor(s / 60)` min), seconds for
the Moon (~1.3 s) and milliseconds for the ISS (~0.02 s). Round trip = `2 × light_time_s`.
For today's value use the Distance card metrics in `/api/dashboard` (`one_way_light_time_s`, `distance_au`, ...).

---

## 8. Chatbot (ECHO check-in)

ECHO is a **Gemini-powered** companion that holds a short daily chat with an astronaut about social connection.
When the chat ends, the backend scores loneliness (3–9) using the Three-Item Loneliness Scale, raises an
alert if needed, and updates the astronaut's Isolation card.

**Rules the UI must follow**

| Rule | Value | From the API |
|---|---|---|
| Replies needed before scoring | 3 astronaut messages | `min_turns`, `can_complete` |
| Maximum replies | 10 astronaut messages | `max_turns`, `must_complete` |
| Message length | 1–2000 characters | `422` otherwise |
| ECHO reply time | usually 1–3 s (at most ~40 s if Gemini is slow and the backup model is used) | show a typing indicator |

### GET `/api/isolation/method`

How check-ins are scored. Use it for an "About this score" info panel.

**200 response:**

```json
{
  "instrument": "Three-Item Loneliness Scale, rated from a conversational AI check-in",
  "source": "Hughes, Waite, Hawkley & Cacioppo (2004), Research on Aging 26(6)",
  "items": [
    "How often do you feel that you lack companionship?",
    "How often do you feel left out?",
    "How often do you feel isolated from others?"
  ],
  "item_scale": { "1": "Hardly ever", "2": "Some of the time", "3": "Often" },
  "score_range": [3, 9],
  "min_turns": 3,
  "max_turns": 10,
  "min_confidence": 0.6,
  "bands": {
    "green": "3-5",
    "amber": ">= 6",
    "red": ">= 7 for 3 consecutive days, or a safety concern (our rule, illustrative)",
    "unreliable": "confidence < 0.6: stored, capped at amber, not used on the card"
  }
}
```

### POST `/api/isolation/{astronautId}/sessions`

Starts a chat. No request body. Returns the session and ECHO's opening message.

| Query | Type | Required | Notes |
|---|---|---|---|
| `day` | int 1–30 | no | mission day this check-in counts for; defaults to the saved current day |

```http
POST /api/isolation/A/sessions?day=12
```

**201 response:** `StartSessionResponse`

```json
{
  "session": {
    "id": "444035a3-559b-4667-ab28-eccee8589d0e",
    "astronaut_id": "A",
    "mission_day": 12,
    "status": "active",
    "created_at": "2026-11-14T17:38:26.570026Z",
    "completed_at": null
  },
  "messages": [
    {
      "id": "7eed30cf-aff0-49af-9130-e8c292a6d17a",
      "session_id": "444035a3-559b-4667-ab28-eccee8589d0e",
      "role": "assistant",
      "content": "Hi Astronaut A, it's ECHO with your day 12 check-in. How have things been between you and the rest of the crew lately?",
      "created_at": "2026-11-14T17:38:26.570156Z"
    }
  ],
  "min_turns": 3,
  "max_turns": 10
}
```

**Errors:** `404` unknown astronaut, `422` bad day, `503` chatbot not configured.

### POST `/api/isolation/{astronautId}/sessions/{sessionId}/messages`

Sends what the astronaut typed; returns ECHO's reply (generated by Gemini).

**Request body:**

```json
{ "content": "Honestly it's been a bit quiet. The crew is busy with experiments so we mostly eat separately." }
```

**200 response:** `ChatTurnResponse`

```json
{
  "session_id": "444035a3-559b-4667-ab28-eccee8589d0e",
  "reply": {
    "id": "634099ac-c13a-42c4-a62c-f44ba9606147",
    "session_id": "444035a3-559b-4667-ab28-eccee8589d0e",
    "role": "assistant",
    "content": "It sounds like the mission schedule is already pulling everyone into their own tasks, making it tough to even share a meal. When things get that quiet, do you feel like you still have people, on board or back home, that you can really talk to?",
    "created_at": "2026-11-14T17:38:30.571455Z"
  },
  "astronaut_turns": 1,
  "can_complete": false,
  "must_complete": false
}
```

- `can_complete: true` → show the **"Finish check-in"** button (after 3 replies).
- `must_complete: true` → the reply limit is reached; hide the input and finish the check-in.
- **If this call fails (e.g. `503`), nothing is saved:** neither the astronaut's message nor a reply. It is safe to
  send the same text again.

**Errors:** `404` session not found, `409` session already completed or reply limit reached,
`422` empty or >2000-character message, `503` Gemini unavailable (see [Errors](#10-errors)).

### POST `/api/isolation/{astronautId}/sessions/{sessionId}/complete`

Ends the chat and returns the score. No request body. **Safe to call twice**: it returns the same result.

**200 response:** `LonelinessAssessment`

```json
{
  "id": "f9af0890-26d3-491c-8b69-80fd3fdce6a9",
  "session_id": "444035a3-559b-4667-ab28-eccee8589d0e",
  "astronaut_id": "A",
  "mission_day": 12,
  "q1": 3,
  "q2": 2,
  "q3": 2,
  "score": 7,
  "confidence": 0.85,
  "reliable": true,
  "safety_concern": false,
  "level": "amber",
  "consecutive_days_at_or_above_7": 1,
  "rationale": "The astronaut eats separately from the crew and feels left out when plans happen during their sleep shift.",
  "evidence": [
    "The crew is busy with experiments so we mostly eat separately.",
    "Sometimes I feel left out when the others plan things during my sleep shift.",
    "no evidence"
  ],
  "alert": {
    "rule": "I.loneliness",
    "hazard": "I",
    "level": "amber",
    "what": "Loneliness score 7/9 (≥6 = elevated).",
    "why": "Prolonged isolation and confinement raise the risk of mood and performance decline.",
    "action": "Plan social time with crew and a call home; check in again tomorrow.",
    "source": "Three-Item Loneliness Scale (Hughes et al., 2004) rated from an AI check-in; red rules are ours (illustrative)"
  },
  "model": "gemini-3.5-flash",
  "created_at": "2026-11-14T17:38:41.571868Z"
}
```

| Field | Meaning |
|---|---|
| `q1`, `q2`, `q3` | Item ratings 1–3: lack of companionship, feeling left out, feeling isolated |
| `score` | `q1 + q2 + q3`, 3–9 |
| `level` | green 3–5 · amber ≥ 6 · red ≥ 7 on 3 days in a row, or a safety concern |
| `confidence` / `reliable` | `reliable` is false when confidence < 0.6: the score is saved but does **not** change the Isolation card |
| `safety_concern` | ECHO detected hopelessness / self-harm / not coping → always red |
| `evidence` | quote per item (same order as q1–q3), or `"no evidence"` |
| `alert` | ready-to-show alert for this check-in |

**Errors:** `404` session not found, `409` fewer than 3 astronaut replies
(`"Need at least 3 astronaut replies to score the check-in (have 1)"`), `503` Gemini unavailable.

### GET `/api/isolation/{astronautId}/sessions/{sessionId}`

Full transcript and the score (if completed). Use it to resume a chat after a page reload or to show a past chat.

**200 response:** `ChatSessionDetail`

```json
{
  "session": {
    "id": "444035a3-559b-4667-ab28-eccee8589d0e",
    "astronaut_id": "A",
    "mission_day": 12,
    "status": "completed",
    "created_at": "2026-11-14T17:38:26.570026Z",
    "completed_at": "2026-11-14T17:38:41.571891Z"
  },
  "messages": [
    { "id": "7eed30cf-...", "session_id": "444035a3-...", "role": "assistant", "content": "Hi Astronaut A, it's ECHO with your day 12 check-in. ...", "created_at": "2026-11-14T17:38:26.570156Z" },
    { "id": "04837757-...", "session_id": "444035a3-...", "role": "astronaut", "content": "Honestly it's been a bit quiet. ...", "created_at": "2026-11-14T17:38:27.570626Z" }
  ],
  "assessment": { "...": "LonelinessAssessment, or null while the session is active" }
}
```

### GET `/api/isolation/{astronautId}`

Loneliness score history: one simulated score per day (1–30) followed by every ECHO check-in.

**200 response:** `IsolationHistory` (shortened)

```json
{
  "astronaut_id": "A",
  "items": [
    { "day": 1, "source": "simulated", "score": 4, "level": null, "confidence": null, "reliable": null, "session_id": null },
    { "day": 12, "source": "ai_checkin", "score": 7, "level": "amber", "confidence": 0.85, "reliable": true, "session_id": "444035a3-559b-4667-ab28-eccee8589d0e" }
  ]
}
```

### Chatbot types

```ts
export type ChatRole = 'assistant' | 'astronaut';

export interface ChatMessage {
  id: string;
  session_id: string;
  role: ChatRole;          // 'assistant' = ECHO
  content: string;
  created_at: string;
}

export interface ChatSession {
  id: string;
  astronaut_id: string;
  mission_day: number;
  status: 'active' | 'completed';
  created_at: string;
  completed_at: string | null;
}

export interface StartSessionResponse {
  session: ChatSession;
  messages: ChatMessage[];
  min_turns: number;
  max_turns: number;
}

export interface ChatTurnResponse {
  session_id: string;
  reply: ChatMessage;
  astronaut_turns: number;
  can_complete: boolean;
  must_complete: boolean;
}

export interface LonelinessAssessment {
  id: string;
  session_id: string;
  astronaut_id: string;
  mission_day: number;
  q1: number; q2: number; q3: number;
  score: number;
  confidence: number;
  reliable: boolean;
  safety_concern: boolean;
  level: Level;
  consecutive_days_at_or_above_7: number;
  rationale: string;
  evidence: string[];
  alert: Alert;
  model: string;
  created_at: string;
}

export interface ChatSessionDetail {
  session: ChatSession;
  messages: ChatMessage[];
  assessment: LonelinessAssessment | null;
}

export interface IsolationHistory {
  astronaut_id: string;
  items: {
    day: number;
    source: 'simulated' | 'ai_checkin';
    score: number;
    level: Level | null;
    confidence: number | null;
    reliable: boolean | null;
    session_id: string | null;
  }[];
}
```

---

## 9. Building the Gemini chatbot in the frontend

### 9.1 Architecture: the frontend never talks to Gemini

```
 Browser (Angular)                 RIDGE backend (FastAPI)                     Google Gemini API
 ─────────────────                 ───────────────────────                     ─────────────────
 Chat UI ── POST /sessions ──────▶ creates session (Supabase) ─────────────────
         ◀── opening message ───── 
 Chat UI ── POST /messages ──────▶ saves message ── generate reply ──────────▶ gemini-3.x-flash
         ◀── ECHO reply ────────── saves reply   ◀── reply text ──────────────
 Chat UI ── POST /complete ──────▶ rater call (JSON schema) ─────────────────▶ gemini-3.x-flash
         ◀── score + alert ─────── deterministic score + thresholds, saves it
```

- **Do not** put a Gemini API key or the `@google/genai` SDK in the frontend. The key lives only in the
  backend's `.env` (`GEMINI_API_KEY`). A key shipped to the browser can be copied by anyone.
- **Do not** call Supabase directly from the frontend. Row Level Security is off, so the backend is the only
  safe way in.
- The backend handles prompts, the conversation history, safety settings, scoring and storage. The frontend only
  sends the astronaut's text and renders what comes back.

### 9.2 Chat flow

```
[Start check-in] ─▶ POST /sessions ─▶ show messages[0] (ECHO's greeting)
       │
       ▼
 astronaut types ─▶ POST /messages ─▶ append reply
       │                                  │
       │          can_complete == true ───┼──▶ show "Finish check-in" button
       │          must_complete == true ──┴──▶ hide input, call /complete
       ▼
[Finish check-in] ─▶ POST /complete ─▶ show result card (score, level, alert)
                                     ─▶ refresh GET /api/dashboard (Isolation card + alerts change)
```

### 9.3 Angular service

`src/app/api/ridge-api.service.ts`

```ts
import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import {
  AstronautSummary, ChatSessionDetail, ChatTurnResponse, CrewAlert, CrewDetail, DashboardResponse,
  DistanceResponse, IsolationHistory, LonelinessAssessment, StartSessionResponse,
} from './ridge.models';

@Injectable({ providedIn: 'root' })
export class RidgeApiService {
  private http = inject(HttpClient);
  private base = environment.apiBaseUrl; // e.g. 'http://127.0.0.1:8000'

  private dayParams(day?: number): HttpParams {
    return day ? new HttpParams().set('day', day) : new HttpParams();
  }

  // --- Dashboard / astronauts / alerts / distance -------------------------------
  dashboard(day?: number): Observable<DashboardResponse> {
    return this.http.get<DashboardResponse>(`${this.base}/api/dashboard`, { params: this.dayParams(day) });
  }
  crew(day?: number): Observable<AstronautSummary[]> {
    return this.http.get<AstronautSummary[]>(`${this.base}/api/crew`, { params: this.dayParams(day) });
  }
  astronaut(id: string, day?: number): Observable<CrewDetail> {
    return this.http.get<CrewDetail>(`${this.base}/api/crew/${id}`, { params: this.dayParams(day) });
  }
  alerts(day?: number): Observable<CrewAlert[]> {
    return this.http.get<CrewAlert[]>(`${this.base}/api/alerts`, { params: this.dayParams(day) });
  }
  distance(): Observable<DistanceResponse> {
    return this.http.get<DistanceResponse>(`${this.base}/api/distance`);
  }

  // --- ECHO chatbot -----------------------------------------------------------------
  startCheckIn(astronautId: string, day?: number): Observable<StartSessionResponse> {
    return this.http.post<StartSessionResponse>(
      `${this.base}/api/isolation/${astronautId}/sessions`, null, { params: this.dayParams(day) });
  }
  sendMessage(astronautId: string, sessionId: string, content: string): Observable<ChatTurnResponse> {
    return this.http.post<ChatTurnResponse>(
      `${this.base}/api/isolation/${astronautId}/sessions/${sessionId}/messages`, { content });
  }
  completeCheckIn(astronautId: string, sessionId: string): Observable<LonelinessAssessment> {
    return this.http.post<LonelinessAssessment>(
      `${this.base}/api/isolation/${astronautId}/sessions/${sessionId}/complete`, null);
  }
  checkInDetail(astronautId: string, sessionId: string): Observable<ChatSessionDetail> {
    return this.http.get<ChatSessionDetail>(`${this.base}/api/isolation/${astronautId}/sessions/${sessionId}`);
  }
  isolationHistory(astronautId: string): Observable<IsolationHistory> {
    return this.http.get<IsolationHistory>(`${this.base}/api/isolation/${astronautId}`);
  }
}
```

### 9.4 Chat component logic (signals)

`src/app/check-in/check-in.component.ts`, showing the state handling (template left to your design):

```ts
import { Component, inject, input, output, signal, computed } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { RidgeApiService } from '../api/ridge-api.service';
import { ChatMessage, LonelinessAssessment } from '../api/ridge.models';

const STORAGE_KEY = (astronautId: string) => `echo-session-${astronautId}`;

@Component({ selector: 'app-check-in', templateUrl: './check-in.component.html', standalone: true })
export class CheckInComponent {
  private api = inject(RidgeApiService);

  astronautId = input.required<string>();
  day = input<number | undefined>();
  completed = output<LonelinessAssessment>();          // parent refreshes the dashboard

  sessionId = signal<string | null>(null);
  messages = signal<ChatMessage[]>([]);
  draft = signal('');
  waiting = signal(false);                             // ECHO is "typing"
  canComplete = signal(false);
  mustComplete = signal(false);
  result = signal<LonelinessAssessment | null>(null);
  error = signal<string | null>(null);

  canSend = computed(() =>
    !!this.sessionId() && !this.waiting() && !this.mustComplete() && !this.result()
    && this.draft().trim().length > 0 && this.draft().length <= 2000);

  ngOnInit() {
    // Resume an unfinished chat after a reload.
    const saved = sessionStorage.getItem(STORAGE_KEY(this.astronautId()));
    if (saved) {
      this.api.checkInDetail(this.astronautId(), saved).subscribe({
        next: d => {
          if (d.session.status === 'completed') { sessionStorage.removeItem(STORAGE_KEY(this.astronautId())); return; }
          this.sessionId.set(d.session.id);
          this.messages.set(d.messages);
          const turns = d.messages.filter(m => m.role === 'astronaut').length;
          this.canComplete.set(turns >= 3);
          this.mustComplete.set(turns >= 10);
        },
        error: () => sessionStorage.removeItem(STORAGE_KEY(this.astronautId())),
      });
    }
  }

  start() {
    this.error.set(null);
    this.waiting.set(true);
    this.api.startCheckIn(this.astronautId(), this.day()).subscribe({
      next: res => {
        this.sessionId.set(res.session.id);
        this.messages.set(res.messages);
        sessionStorage.setItem(STORAGE_KEY(this.astronautId()), res.session.id);
        this.waiting.set(false);
      },
      error: e => this.fail(e),
    });
  }

  send() {
    if (!this.canSend()) return;
    const text = this.draft().trim();
    const sid = this.sessionId()!;
    // Optimistic: show the astronaut's message immediately.
    const pending: ChatMessage = {
      id: `local-${Date.now()}`, session_id: sid, role: 'astronaut', content: text,
      created_at: new Date().toISOString(),
    };
    this.messages.update(m => [...m, pending]);
    this.draft.set('');
    this.waiting.set(true);
    this.error.set(null);

    this.api.sendMessage(this.astronautId(), sid, text).subscribe({
      next: res => {
        this.messages.update(m => [...m, res.reply]);
        this.canComplete.set(res.can_complete);
        this.mustComplete.set(res.must_complete);
        this.waiting.set(false);
        if (res.must_complete) this.finish();
      },
      error: e => {
        // Nothing was saved (the backend stores the message only once ECHO has replied),
        // so remove the optimistic bubble and put the text back for the astronaut to resend.
        this.messages.update(m => m.filter(x => x.id !== pending.id));
        this.draft.set(text);
        this.fail(e);
      },
    });
  }

  finish() {
    const sid = this.sessionId();
    if (!sid) return;
    this.waiting.set(true);
    this.api.completeCheckIn(this.astronautId(), sid).subscribe({
      next: assessment => {
        this.result.set(assessment);
        this.waiting.set(false);
        sessionStorage.removeItem(STORAGE_KEY(this.astronautId()));
        this.completed.emit(assessment);
      },
      error: e => this.fail(e),
    });
  }

  private fail(e: HttpErrorResponse) {
    this.waiting.set(false);
    const detail = typeof e.error?.detail === 'string' ? e.error.detail : null;
    if (e.status === 503) {
      this.error.set(detail?.includes('rate limit')
        ? 'ECHO is busy right now (AI quota reached). Please try again in a minute.'
        : 'ECHO is unavailable right now. Please try again later.');
    } else if (e.status === 409) {
      this.error.set(detail ?? 'This check-in cannot continue.');
    } else if (e.status === 404) {
      sessionStorage.removeItem(STORAGE_KEY(this.astronautId()));
      this.sessionId.set(null);
      this.error.set('This check-in was not found. Please start a new one.');
    } else {
      this.error.set('Something went wrong. Please try again.');
    }
  }
}
```

In the parent (dashboard) page, refresh after a check-in:

```ts
onCheckInCompleted() {
  this.api.dashboard(this.selectedDay()).subscribe(d => this.dashboard.set(d));
}
```

### 9.5 UX guidelines

1. **Typing indicator.** ECHO usually replies in 1–3 seconds. Show "ECHO is typing…" while `waiting()` is true and
   disable the send button so messages are not sent twice.
2. **Progress.** Show "Reply 2 of at least 3" until `can_complete`, then show a **Finish check-in** button.
   After 10 replies (`must_complete`) finish automatically.
3. **Result card.** After `/complete` show `score`/9 with the level colour, `alert.what` and `alert.action`.
   Optionally show the three `evidence` quotes under the item names from `/api/isolation/method`.
4. **Low confidence.** If `reliable` is false, show "Not enough detail to score confidently, try another
   check-in tomorrow". The dashboard card will not change.
5. **Safety concern.** If `safety_concern` is true, show a clear, calm banner such as "Your flight surgeon will
   follow up with you today." Don't show it as a scary error. ECHO's own reply will already say this.
6. **Privacy.** Transcripts are sensitive. Show them only on the astronaut's own check-in screen (and to the
   flight surgeon role, if you add one). The dashboard only needs the score and alert.
7. **Free-tier limits.** The backend uses the Gemini free tier, which has small per-minute and per-day quotas.
   Each check-in uses ~4–11 Gemini calls. If you get `503` with "rate limit", ask the user to wait and retry; don't
   retry automatically in a loop.
8. **Feature flag.** Call `GET /health` at startup. If `ai_checkin` is `false`, hide the check-in button and show
   "Check-ins unavailable".

### 9.6 Quick manual test with curl

```bash
BASE=http://127.0.0.1:8000
SID=$(curl -s -X POST "$BASE/api/isolation/A/sessions?day=12" | python3 -c "import sys,json;print(json.load(sys.stdin)['session']['id'])")
curl -s -X POST "$BASE/api/isolation/A/sessions/$SID/messages" -H 'Content-Type: application/json' -d '{"content":"It has been quiet, we mostly eat separately."}'
curl -s -X POST "$BASE/api/isolation/A/sessions/$SID/messages" -H 'Content-Type: application/json' -d '{"content":"I miss my family, calls feel awkward with the delay."}'
curl -s -X POST "$BASE/api/isolation/A/sessions/$SID/messages" -H 'Content-Type: application/json' -d '{"content":"Sometimes I feel left out during my sleep shift."}'
curl -s -X POST "$BASE/api/isolation/A/sessions/$SID/complete"
```

---

## 10. Errors

Business errors return JSON with a string `detail`:

```json
{ "detail": "Unknown astronaut 'Z'" }
```

Request validation errors (wrong type, empty message, missing body) return `422` with a **list** in `detail`
(FastAPI format):

```json
{
  "detail": [
    { "type": "string_too_short", "loc": ["body", "content"], "msg": "String should have at least 1 character", "input": "", "ctx": { "min_length": 1 } }
  ]
}
```

| Status | When | Example `detail` | What the UI should do |
|---|---|---|---|
| 404 | Unknown astronaut | `Unknown astronaut 'Z'` | Show "not found" |
| 404 | Unknown chat session (or it belongs to another astronaut) | `Unknown check-in session '…'` | Forget the stored session id, offer "Start new check-in" |
| 409 | Session already completed | `This check-in session is already completed; start a new one` | Show the result / offer a new check-in |
| 409 | Reply limit reached | `Reply limit of 10 reached; complete the check-in to get a score` | Call `/complete` |
| 409 | Too few replies to score | `Need at least 3 astronaut replies to score the check-in (have 1)` | Keep chatting |
| 422 | Day outside 1–30 | `Mission day 31 is outside 1-30` | Clamp the slider to 1–`mission_days` |
| 422 | Invalid body | list (see above) | Show the field error |
| 503 | Chatbot not configured | `AI check-in companion unavailable: GEMINI_API_KEY is not configured` | Hide the chatbot |
| 503 | Gemini quota hit | `AI check-in companion unavailable: Gemini rate limit reached (free tier quota), retry shortly` | "ECHO is busy, try again in a minute" |
| 503 | Gemini down / blocked | `AI check-in companion unavailable: …` | "ECHO is unavailable right now" |
| 503 | Database down | `Database temporarily unavailable; please retry` | Retry button |

---

## 11. Mobility & Balance Check

Three short tests (about 2 minutes) on the **Gravity** card. The Angular page uses **MediaPipe Pose** in the browser to
draw the skeleton and compute the numbers; **no video is sent**, only the final numbers below. It measures movement
(balance, leg strength, knee range of motion). It does **not** assess bone health or bone loss.

| Test | What the astronaut does | Numbers to send |
|---|---|---|
| `balance` | Stand on one leg, hands on hips, up to 30 s | `balance_hold_s`, `sway_pct_height` (RMS hip-centre sway as % of body height) |
| `sit_to_stand` | 5 sit-to-stands, arms crossed, as fast as is safe | `sit_to_stand_5x_s` |
| `squat_rom` | 3 slow bodyweight squats, side-on to the camera | `knee_flexion_deg` (deepest knee bend) |

Also send `pose_confidence` (mean keypoint visibility, 0 to 1). Below the `min_pose_confidence` from `/api/mobility/method`
(0.6) the check is saved but not used (`counted: false`); ask the astronaut to retake in good light.

### POST `/api/mobility/{astronautId}?day=`

```json
{ "balance_hold_s": 22, "sway_pct_height": 1.4, "sit_to_stand_5x_s": 10.8, "knee_flexion_deg": 112, "pose_confidence": 0.91 }
```

Returns `201` with `{ check, counted, result, message }`. `result` has `level` (`green|amber|red`), one entry per test
(`values`, `baseline` = the astronaut's first reliable check, `change_pct` = % worse than that, `note`) and the `alert`
(what / why / action / source). A check applies to its mission day and every later day.

### GET `/api/mobility/{astronautId}`

`{ astronaut_id, checks[], latest }`, for a history chart.

### On the Gravity card

`GET /api/crew/{id}` and `/api/dashboard`: the Gravity card `metrics.mobility` is `null` until a reliable check exists, then
`{ level, checks_used, last_check_day, tests[] }`. The card level is the worst of the cardio rule and `G.mobility`.
Thresholds are illustrative; see `GET /api/mobility/method`.

# Mobility & Balance Check (additive endpoints)

Three short movement tests (about 2 minutes): single-leg balance, 5x sit-to-stand and a squat knee bend. The Angular
page uses **MediaPipe Pose in the browser** to draw the skeleton and measure; the backend only receives the final
numbers and scores them. No video leaves the device, no YOLO, and nothing heavy runs on the server.

**It measures movement (balance, leg strength, knee bend). It does not assess bone health or bone loss.**

These endpoints are **extra**: they are not in the v2 guide and the frontend does not have to change. Once a check
exists the result flows into the existing screens by itself:

- the **Gravity** hazard gets a driver, "Mobility & balance check" (`GET /api/assessment/hazards`; its `metric` is
  omitted so nothing needs special handling), and the score moves with it;
- a finding `mobility:<crewId>` (`severity` watch or alert, `primaryMetric: "legStrength"`) appears in
  `GET /api/insights` when the latest check is flagged, with evidence per test and recommended actions. It resolves,
  reopens and logs like any other finding.

## Endpoints

### `GET /api/mobility/method`
The tests, what to send, thresholds, `minPoseConfidence` (0.6) and the limits text. Use it for an info panel.

### `POST /api/mobility/{crewId}` (201)
```json
{ "balanceHoldS": 22, "swayPctHeight": 1.4, "sitToStandS": 10.8, "kneeFlexionDeg": 112, "poseConfidence": 0.91 }
```

| Field | Range | Meaning |
|---|---|---|
| `balanceHoldS` | 0 to 30 | seconds on one leg (stop at 30) |
| `swayPctHeight` | 0 to 50 | RMS sway of the hip centre, as % of body height |
| `sitToStandS` | above 1, up to 120 | seconds for 5 sit-to-stands |
| `kneeFlexionDeg` | 0 to 150 | deepest knee bend; above 150 is a tracking error and returns 422 |
| `poseConfidence` | 0 to 1 | mean keypoint visibility; below 0.6 the check is saved but not used |

Response:
```json
{
  "check": { "id": "mob-ahmad-4fe0d5ea", "crewId": "ahmad", "day": 142, "at": 3394.85, "measurements": { "...": 0 }, "reliable": true },
  "counted": true,
  "message": "Check saved.",
  "result": {
    "status": "nominal | watch | alert",
    "tests": [
      { "test": "balance | sit_to_stand | squat_rom", "label": "Single-leg balance", "status": "watch",
        "values": { "balanceHoldS": 6, "swayPctHeight": 2.4 },
        "baseline": { "balanceHoldS": 30, "swayPctHeight": 1 },
        "changePct": { "balanceHoldS": 80, "swayPctHeight": 140 },
        "note": "Worse than expected: repeat the test and review." }
    ],
    "checksUsed": 2, "lastCheckAt": 3394.85, "lastCheckDay": 142
  }
}
```
`baseline` and `changePct` are `null` for the first check (each later check is compared with the first reliable one).
If `counted` is false, `result` is `null`: show `message` and ask for a retake in good light, side-on, whole body in view.
Errors: `404` unknown astronaut, `422` out-of-range values (`{"detail": "field: message"}`).

### `GET /api/mobility/{crewId}`
`{ crewId, checks[], latest }` for a history chart. `latest` is the result of the newest reliable check, or `null`.

## Scoring (illustrative, ours; not clinical)

Each test is judged against absolute limits and against the astronaut's own first reliable check (25 % worse is
`watch`, 50 % worse is `alert`). Balance hold: under 10 s `watch`, under 5 s `alert`. Sit-to-stand: 12 s `watch`,
15 s `alert`. Squat depth: under 100° `watch`, under 80° `alert`. Overall status is the worst test.

## Build the page in Angular

A working reference is served at **`/demo/mobility/`** (source: `app/static/mobility/index.html`). Port its logic into a
component, using `@mediapipe/tasks-vision` (`PoseLandmarker`, video mode, lite model, one pose).

1. **Landmarks used** (of 33): nose, shoulders (11, 12), hips (23, 24), knees (25, 26), ankles (27, 28). Work in
   **pixels** (x times video width, y times video height) so angles are not distorted.
2. **Knee bend** = 180 minus the hip-knee-ankle angle, on the better-seen leg. **Ignore any frame above 150°**: it is a
   tracking error, almost always a foreshortened leg.
3. **Balance**: a foot is lifted when the ankle height gap is more than 8 % of body height (nose to mid-ankle) for 0.3 s.
   `balanceHoldS` runs until it touches down (more than 0.5 s) or 30 s. `swayPctHeight` is the RMS distance of the
   hip-centre from its mean during the hold, as % of body height.
4. **Sit-to-stand** (start seated): leaving the seat is knee bend below 45°, a stand is below 25°, sitting again is above
   55°. `sitToStandS` is the time from leaving the seat to the 5th stand.
5. **Squat**: a rep is bend above 50° then back below 25°. `kneeFlexionDeg` is the median of 3 rep peaks.
6. `poseConfidence`: mean visibility of hips, knees and ankles over the tests.
7. **Camera placement matters**: stand or sit **side-on** with the whole body in view. A front view makes the 2D knee
   angle unreliable. Show a "turn side-on / step back" hint when tracking is poor.

## On your side

- Pin `@mediapipe/tasks-vision` and host its WASM files and `pose_landmarker_lite.task` in `assets/` so it works offline
  (the reference page loads them from a CDN). Try `delegate: "GPU"` first and fall back to `"CPU"`.
- The camera needs https or `localhost`. Add your Angular origin to the backend's `CORS_ORIGINS` (GET, POST, PUT only).
- Keep visible: "Decision-support prototype, not a medical device. Measures movement, not bone health. Video stays on this
  device."
- Show the returned `status` per test (nominal, watch, alert) with its `note`.
- Test without a camera: `/demo/mobility/?video=/path/to/clip.mp4` (same origin) or the file picker.

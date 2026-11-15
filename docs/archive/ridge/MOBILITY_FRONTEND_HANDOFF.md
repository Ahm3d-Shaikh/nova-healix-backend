# Mobility & Balance Check: handoff for the Angular team

A working reference page lives in this repo: [`app/static/mobility/index.html`](../app/static/mobility/index.html).
Run the backend and open **http://127.0.0.1:8000/demo/mobility/** (camera works on `localhost` and on https; not on plain http elsewhere).
Port its logic into an Angular component; the API contract is in [FRONTEND_API_GUIDE.md](FRONTEND_API_GUIDE.md) section 11.

## How it works

1. **MediaPipe Pose runs in the browser** (`@mediapipe/tasks-vision`, `PoseLandmarker`, running mode `VIDEO`, `numPoses: 1`, lite model).
   Video never leaves the device. Nothing pose-related runs on the server, so there is no model to deploy on Railway.
2. Each frame gives 33 landmarks. The page uses 9 of them: nose, shoulders (11, 12), hips (23, 24), knees (25, 26), ankles (27, 28).
3. Three small state machines turn landmarks into five numbers (below).
4. `POST /api/mobility/{astronautId}?day=N` with those numbers; the response is the scored result for the Gravity card.

## The three tests and how each number is computed

All geometry is in **pixels** (landmark x times video width, y times video height) so angles are not distorted.

| Test | Start | Numbers |
|---|---|---|
| Single-leg balance, max 30 s | 3 s countdown, then the astronaut lifts a foot | `balance_hold_s`: time from the foot lifting (ankle height gap > 8% of body height for 0.3 s) until it touches down (> 0.5 s) or 30 s. `sway_pct_height`: RMS distance of the hip-centre from its mean during the hold, as % of body height (nose to mid-ankle). |
| 5x sit-to-stand | Astronaut starts seated | `sit_to_stand_5x_s`: time from leaving the seat (knee bend < 45 deg) to the 5th full stand (knee bend < 25 deg; sitting again is knee bend > 55 deg). |
| Squat knee bend, 3 reps | 3 slow squats, side-on | `knee_flexion_deg`: median of the three peaks. |

- **Knee bend** = 180 minus the hip-knee-ankle angle, on whichever leg has the higher visibility.
- **`pose_confidence`**: mean visibility of hips, knees and ankles over the tests (the API ignores a check below 0.6 and asks for a retake).
- **Ignore any frame with knee bend above 150 deg**: it is a tracking error, almost always a foreshortened leg. The API rejects `knee_flexion_deg` above 150 with a 422.
- **Camera placement matters**: stand or sit **side-on** with the whole body in view. A front view makes the 2D knee angle unreliable (we saw 34 deg vs 94 deg on two legs of the same person on a front-ish clip).
  Show a "step back / turn side-on" hint when tracking is below 60%.

## Things to change on your side

- Move the state machines into a service, use signals for the live values, and keep the thresholds in one constants file.
- Pin `@mediapipe/tasks-vision` in `package.json` and copy the WASM files and `pose_landmarker_lite.task` into your `assets/` so the app works offline (the reference page loads them from a CDN for simplicity).
- Call the API through your own base URL. Add your Angular origin to `CORS_ORIGINS` on the backend (only `GET` and `POST` are allowed).
- Try `delegate: "GPU"` first and fall back to `"CPU"` (the page does this).
- Add a skeleton overlay and a clear 3-2-1 countdown, and show the returned `level` per test (green, amber, red) with the `note`.
- The thresholds in the response (`GET /api/mobility/method`) are illustrative; do not present them as clinical.

## Must keep in the UI

- "Decision-support prototype, not a medical device."
- "Measures movement (balance, leg strength, knee bend), not bone health."
- Camera permission wording that says video stays on the device.

## Testing without a camera

Open the page with a video: `/demo/mobility/?video=/path/to/clip.mp4`, or use the file picker on the page.
For `?video=`, the clip must be served from the same origin.

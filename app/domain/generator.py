"""Deterministic simulated crew data (frontend `generator.ts`): same seed, same numbers.

Produces hourly vitals, daily sleep / dose / CO2, weekly and monthly tests, exercise sessions
and daily check-ins for one astronaut, over `GENERATED_DAYS` days.
"""

import math
from dataclasses import dataclass, field

from app.domain.mission_plan import (
    GENERATED_DAYS,
    GENERATED_HOURS,
    MISSION_EVENTS,
    at,
    hour_to_day,
)
from app.domain.personas import PERSONAS, Persona, story_value
from app.domain.prng import ArNoise, Rng, clamp, js_round, round_to
from app.domain.stats import Series
from app.schemas.telemetry import CheckIn

SPE_DAYS = frozenset({97, 98})
DAYS_PER_MONTH = 30.44


@dataclass
class ExerciseSession:
    day: int
    start: float
    end: float
    done: bool


@dataclass
class CrewBundle:
    crew_id: str
    series: dict[str, Series] = field(default_factory=dict)
    check_ins: list[CheckIn] = field(default_factory=list)
    exercise: list[ExerciseSession] = field(default_factory=list)
    # Per-hour activity context (index = mission hour)
    asleep: list[float] = field(default_factory=list)
    exercise_load: list[float] = field(default_factory=list)
    eva: list[float] = field(default_factory=list)


def _eva_days_for(crew_id: str) -> set[int]:
    return {hour_to_day(e.start) for e in MISSION_EVENTS if e.kind == "eva" and crew_id in e.crew_ids}


def _sleep_start_for(p: Persona, night_of_day: int) -> float:
    # Ahmad's planned sleep shift for EVA-3 prep: nights D136-D144 start 2 h earlier.
    if p.astronaut.id == "ahmad" and 136 <= night_of_day <= 144:
        return p.astronaut.sleep_start_hour - 2
    return p.astronaut.sleep_start_hour


def _paint(arr: list[float], start: float, end: float, weight: float = 1.0) -> None:
    """Spread a [start, end) interval over hourly buckets as fractional coverage."""
    for h in range(max(0, math.floor(start)), min(len(arr), math.ceil(end))):
        overlap = min(end, h + 1) - max(start, h)
        if overlap > 0:
            arr[h] = min(1.0, arr[h] + overlap * weight)


def generate_crew(crew_id: str) -> CrewBundle:  # noqa: PLR0912, PLR0915 - a flat port of the reference generator
    p = PERSONAS[crew_id]
    P = p.params  # noqa: N806
    rng = Rng(f"nhx-1:{crew_id}")
    eva_days = _eva_days_for(crew_id)

    asleep = [0.0] * GENERATED_HOURS
    exercise_load = [0.0] * GENERATED_HOURS
    eva = [0.0] * GENERATED_HOURS
    shelter = [0.0] * GENERATED_HOURS

    series: dict[str, Series] = {}

    def push(k: str, t: float, v: float) -> None:
        series.setdefault(k, Series()).add(t, v)

    # -- Daily layer: sleep, exercise, dose, CO2, musculoskeletal, questionnaires ------------------
    sleep_noise = ArNoise(rng, 0.38, 0.35)
    eff_noise = ArNoise(rng, 2.4, 0.35)
    co2_noise = ArNoise(rng, 0.16, 0.5)
    cumulative_dose = 0.0
    bone_loss_pct = 0.0
    lean_loss_pct = 0.0

    for d in range(1, GENERATED_DAYS + 1):
        # The night ending on the morning of day d starts the evening of day d-1.
        start = at(d - 1, _sleep_start_for(p, d - 1))
        dur = P["sleepH"] + story_value(p, "sleepH", d) + sleep_noise.step()
        eff = P["sleepEff"] + story_value(p, "sleepEff", d) + eff_noise.step()
        if d == 97:
            dur -= 3.1 if crew_id == "sabaina" else 2.4  # SPE alarm at 03:00
            eff -= 14
        elif d == 98:
            dur -= 1.6  # night in storm shelter
            eff -= 12
        elif (d - 1) in eva_days:
            dur += 0.5  # recovery night after EVA
        if d <= 4:
            dur -= 1.0 - d * 0.2  # space adaptation
            eff -= 8 - d * 2
        dur = clamp(dur, 3.2, 9.5)
        eff = clamp(eff, 58, 97)
        if d == 97:
            _paint(asleep, start, at(97, 3))
        else:
            _paint(asleep, start, start + dur)
        wake = at(97, 3) if d == 97 else start + dur
        if d > 1:
            push("sleepDuration", wake, round_to(dur, 2))
            push("sleepEfficiency", wake, round_to(eff, 1))

        # Exercise (skipped on EVA and SPE days, and by compliance)
        skip_p = P["exerciseSkip"] + story_value(p, "exerciseSkip", d)
        ex_start = at(d, p.astronaut.exercise_hour)
        forced_skip = d in p.skipped_exercise
        done = d not in eva_days and d not in SPE_DAYS and not rng.chance(skip_p) and not forced_skip
        if d > 2 and done:
            _paint(exercise_load, ex_start, ex_start + 1, 1)
            _paint(exercise_load, ex_start + 1, ex_start + 1.5, 0.5)
            # Leg press load cells: estimated 1RM, tracks lean mass loss (+ extra for skipped training).
            strength = (
                P["strength"] * (1 - (lean_loss_pct * 1.4) / 100 + story_value(p, "strengthPct", d)) + rng.gauss() * 1.6
            )
            push("legStrength", ex_start + 1.5, round_to(strength, 1))

        # Radiation: cumulative effective dose at start of day d
        push("radDose", at(d, 0), round_to(cumulative_dose, 2))
        daily = 1.78 * P["shield"] * (1 + 0.04 * rng.gauss())
        if d in eva_days:
            daily += 0.35
        if d == 97:
            daily += P["speDose"] * 0.82
        if d == 98:
            daily += P["speDose"] * 0.18
        cumulative_dose += daily

        # Personal CO2 exposure (24 h mean), scrubber degradation from D140
        co2 = 2.45 + P["co2Offset"] + co2_noise.step()
        if d >= 140:
            co2 += 0.85 + (d - 140) * 0.12
        if d in (61, 62):
            co2 += 0.45
        push("co2", at(d, 12), round_to(clamp(co2, 1.4, 5.5), 2))

        # Musculoskeletal: integrate daily loss, measure weekly
        bone_loss_pct += (P["boneRate"] + story_value(p, "boneRateExtra", d)) / DAYS_PER_MONTH
        lean_loss_pct += (P["leanRate"] + story_value(p, "leanRateExtra", d)) / DAYS_PER_MONTH
        if d % 7 == 1:
            push("boneDensity", at(d, 9), round_to(P["bmd"] * (1 - bone_loss_pct / 100) + rng.gauss() * 0.003, 4))
            push("muscleMass", at(d, 9), round_to(P["lean"] * (1 - lean_loss_pct / 100) + rng.gauss() * 0.18, 2))

        # Weekly tablet tests: reaction time (PVT) and near vision
        if d % 7 == 0:
            rt_bump = 22 if d == 98 else 0  # post solar-event fatigue
            push("reactionTime", at(d, 20.5), round_to(P["rt"] + story_value(p, "rt", d) + rng.gauss() * 7 + rt_bump, 0))
            acuity = P["acuity"] + story_value(p, "acuity", d) + rng.gauss() * 0.025
            push("visionAcuity", at(d, 20.6), round_to(js_round(acuity * 20) / 20, 2))
        # Extra vision check the evening Sabaina reported blurred near vision
        if crew_id == "sabaina" and d == 140:
            push("visionAcuity", at(d, 21), round_to(P["acuity"] + story_value(p, "acuity", d), 2))

        # Monthly lab panel (+ extra panel after the solar particle event)
        if d % 30 == 15 or d == 99:
            post = (-0.75 if crew_id == "sabaina" else -0.4) if d == 99 else 0.0
            push("wbc", at(d, 8), round_to(P["wbc"] + story_value(p, "wbc", d) + rng.gauss() * 0.3 + post * 0.6, 2))
            push("lymphocytes", at(d, 8), round_to(P["lymph"] + rng.gauss() * 0.12 + post, 2))
            ntx_rise = 1 + min(0.35, (d / 120) * 0.35) + story_value(p, "ntxPct", d)
            push("boneMarker", at(d, 8.1), round_to(P["ntx"] * ntx_rise + rng.gauss() * 2, 0))

        # Medical supply readiness (ship-wide inventory, deterministic)
        if d % 7 == 2:
            kit = 100 - d * 0.1 - (3 if d > 97 else 0) - (4 if d >= 135 else 0) + math.sin(d / 9) * 0.8
            push("medKit", at(d, 10), round_to(min(100.0, kit), 0))

        # Weekly questionnaires
        if d % 7 == 0:
            spe_bump = 12 if d == 98 else 0
            push("stress", at(d, 19), round_to(clamp(P["stress"] + story_value(p, "stress", d) + rng.gauss() * 4.5 + spe_bump, 0, 100), 0))
            push(
                "workload",
                at(d, 19),
                round_to(clamp(P["workload"] + story_value(p, "workload", d) + rng.gauss() * 4.5 + spe_bump * 0.5, 0, 100), 0),
            )

    # EVA and storm-shelter windows
    for e in MISSION_EVENTS:
        if e.kind == "eva" and crew_id in e.crew_ids:
            _paint(eva, e.start, e.end)
        if e.kind == "spe":
            _paint(shelter, e.start, e.end)

    # Exercise sessions list
    exercise: list[ExerciseSession] = []
    for d in range(3, GENERATED_DAYS + 1):
        start = at(d, p.astronaut.exercise_hour)
        exercise.append(ExerciseSession(d, start, start + 1.5, exercise_load[math.floor(start)] > 0.5))

    # -- Hourly vitals ---------------------------------------------------------------------------------
    n_hr = ArNoise(rng, 2.2)
    n_hrv = ArNoise(rng, 0.07)
    n_spo2 = ArNoise(rng, 0.35, 0.5)
    n_temp = ArNoise(rng, 0.06)
    n_sys = ArNoise(rng, 3)
    n_dia = ArNoise(rng, 2.2)
    n_resp = ArNoise(rng, 0.7, 0.5)
    n_dose = ArNoise(rng, 0.05, 0.6)
    n_noise = ArNoise(rng, 1.3, 0.6)
    n_cab_t = ArNoise(rng, 0.18, 0.8)
    n_rh = ArNoise(rng, 1.6, 0.8)
    spe_start = at(97, 3)
    spe_hours = 32
    for h in range(GENERATED_HOURS):
        d = hour_to_day(h)
        hod = h % 24
        circ = math.cos((2 * math.pi * (hod - 17)) / 24)  # peak late afternoon
        s = asleep[h]
        awake = 1 - s
        ex = exercise_load[h]
        ev = eva[h]
        sh = shelter[h]
        adapt = 1 - d / 14 if d <= 14 else 0
        warm = min(1.0, d / 60)

        hr = (
            P["hr"] + 3 * circ + 6 * awake - 5 * s + 42 * ex + 22 * ev + 6 * sh + 6 * adapt
            + story_value(p, "hr", d) + n_hr.step()
        )
        hrv_factor = (1 + 0.22 * s - 0.45 * ex - 0.3 * ev - 0.15 * sh) * (1 + story_value(p, "hrvPct", d))
        hrv = P["hrv"] * hrv_factor * (1 + n_hrv.step())
        spo2 = P["spo2"] + 0.3 - 0.8 * ex - 0.4 * s + n_spo2.step()
        temp = P["temp"] + 0.3 * circ + 0.5 * ex + 0.3 * ev - 0.2 * s + 0.2 * warm + n_temp.step()
        sys = P["sys"] + 3 * circ + 4 * awake - 9 * s + 22 * ex + 10 * ev + story_value(p, "sys", d) + n_sys.step()
        dia = P["dia"] + 2 * circ + 3 * awake - 7 * s + 4 * ex + 5 * ev + story_value(p, "dia", d) + n_dia.step()
        resp = P["resp"] + 0.5 * circ - 2 * s + 9 * ex + 4 * ev + story_value(p, "resp", d) + n_resp.step()

        push("hr", h, round_to(clamp(hr, 38, 175), 1))
        push("hrv", h, round_to(clamp(hrv, 8, 150), 1))
        push("spo2", h, round_to(clamp(spo2, 90, 100), 1))
        push("coreTemp", h, round_to(clamp(temp, 35.8, 39.5), 2))
        push("bpSys", h, round_to(clamp(sys, 85, 175), 1))
        push("bpDia", h, round_to(clamp(dia, 48, 110), 1))
        push("resp", h, round_to(clamp(resp, 8, 34), 1))

        # Dosimeter: galactic cosmic ray background ~74 uSv/h, EVA adds, SPE spikes.
        rate = 74 * P["shield"] * (1 + n_dose.step()) + 40 * ev
        if spe_start <= h < spe_start + spe_hours:
            k = h - spe_start
            # Rise over 4 h, slow decay; integrates to roughly the persona's SPE dose.
            shape = (k + 1) / 4 if k < 4 else math.exp(-(k - 4) / 12)
            rate += ((P["speDose"] * 1000) / 15.5) * shape
            if crew_id == "sabaina" and k < 3:
                rate *= 1.6  # late into the shelter
        push("doseRate", h, round_to(rate, 0))

        # Crew-quarters environment
        anomaly = 1 if d >= 140 else 0
        noise = (
            47 * s + 56 * awake + 10 * ex + P["noiseOffset"] + 3 * anomaly
            + s * story_value(p, "nightNoise", d) + n_noise.step()
        )
        push("cabinNoise", h, round_to(clamp(noise, 38, 78), 1))
        push("cabinTemp", h, round_to(22.6 + 0.4 * circ + 0.3 * ex + 0.6 * anomaly + n_cab_t.step(), 2))
        push("cabinHumidity", h, round_to(clamp(44 + 6 * anomaly + 2 * s + n_rh.step(), 25, 75), 1))

    # -- Daily check-ins --------------------------------------------------------------------------------
    check_ins: list[CheckIn] = []
    sleep_series = series.get("sleepDuration", Series())
    missed = p.missed_check_ins
    for wake_t in sleep_series.t:
        d = hour_to_day(wake_t)
        if d in missed:
            rng.next()
            continue
        t = round_to(wake_t + 0.6 + rng.next() * 0.7, 3)
        spe = -0.7 if d in SPE_DAYS else 0.0

        def scale(base: float, ch: str, day: int = d, spe_adj: float = spe) -> int:
            return int(clamp(js_round(base + story_value(p, ch, day) + spe_adj + rng.gauss() * 0.45), 1, 5))

        mood = scale(P["mood"], "mood")
        sleep_q = scale(P["sleepQuality"], "sleepQuality")
        energy = scale(P["energy"], "energy")
        check_ins.append(
            CheckIn(
                id=f"ci-{crew_id}-{d}",
                crew_id=crew_id,
                day=d,
                at=t,
                mood=mood,
                sleep_quality=sleep_q,
                energy=energy,
                symptoms=p.symptoms.get(d, []),  # type: ignore[arg-type]
                note=p.notes.get(d),
            )
        )

    return CrewBundle(crew_id, series, check_ins, exercise, asleep, exercise_load, eva)

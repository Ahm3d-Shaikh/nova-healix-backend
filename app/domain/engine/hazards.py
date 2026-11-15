"""0-100 hazard scores with weighted drivers (frontend `engine/hazards.ts`)."""

import math
from collections.abc import Callable
from dataclasses import dataclass

from app.domain import mobility
from app.domain.engine.context import (
    H_PER_DAY,
    EngineContext,
    combine,
    contrib,
    latest,
    missed_check_in_days,
    recent_check_ins,
    recent_mean,
    score_to_status,
    symptom_count,
    z_high,
    z_low,
)
from app.domain.format import format_delay, format_metric, format_pct, to_fixed
from app.domain.mission_plan import at
from app.domain.prng import clamp, js_round
from app.domain.stats import mean
from app.schemas.assessment import HazardAssessment, HazardDriver
from app.schemas.mission import HAZARD_KEYS, HazardKey
from app.schemas.telemetry import Sample


@dataclass
class Part:
    driver: HazardDriver
    w: float


def _driver(label: str, value: str, c: float, w: float, metric: str | None = None, concern: str | None = None) -> Part:
    c = c if math.isfinite(c) else 0.0
    return Part(
        HazardDriver(
            label=label, value=value, contribution=int(js_round(clamp(c, 0, 100))), metric=metric, concern=concern
        ),
        w,
    )


def _low_driver(
    ctx: EngineContext,
    crew_id: str,
    metric: str,
    days: float,
    label: str,
    w: float,
    concern: str,
    gain: float = 45,
    cap: float = 100,
) -> Part:
    b = ctx.db.baseline(crew_id, metric)
    x = recent_mean(ctx, crew_id, metric, days)
    c = min(cap, contrib(z_low(x, b), gain)) if b and math.isfinite(x) else 0.0
    return _driver(label, format_metric(metric, x) if math.isfinite(x) else "no data", c, w, metric, concern)


def _high_driver(
    ctx: EngineContext,
    crew_id: str,
    metric: str,
    days: float,
    label: str,
    w: float,
    concern: str,
    gain: float = 45,
    cap: float = 100,
) -> Part:
    b = ctx.db.baseline(crew_id, metric)
    x = recent_mean(ctx, crew_id, metric, days)
    c = min(cap, contrib(z_high(x, b), gain)) if b and math.isfinite(x) else 0.0
    return _driver(label, format_metric(metric, x) if math.isfinite(x) else "no data", c, w, metric, concern)


def loss_rate_per_month(ctx: EngineContext, crew_id: str, metric: str) -> tuple[float, float]:
    """(percent change since first measurement, percent per month)."""
    s = ctx.db.series(crew_id, metric)
    last = s.last_at(ctx.hour)
    if not len(s) or last is None or last[0] <= s.t[0]:
        return 0.0, 0.0
    pct = ((last[1] - s.v[0]) / s.v[0]) * 100
    months = (last[0] - s.t[0]) / H_PER_DAY / 30.44
    return pct, pct / months


def crew_dose_median(ctx: EngineContext) -> float:
    doses = sorted((latest(ctx, a.id, "radDose") or (0, 0))[1] for a in ctx.db.crew())
    return (doses[1] + doses[2]) / 2


def _radiation(ctx: EngineContext, crew_id: str) -> list[Part]:
    dose = (latest(ctx, crew_id, "radDose") or (0, 0))[1]
    cum_pct = (dose / ctx.career_limit_msv) * 100
    excess = dose - crew_dose_median(ctx)
    rate_now = mean(ctx.db.series(crew_id, "doseRate").slice(ctx.hour - 3, ctx.hour).v)
    lym = ctx.db.series(crew_id, "lymphocytes").last_at(ctx.hour)
    lym_b = ctx.db.baseline(crew_id, "lymphocytes")
    lym_c = contrib(z_low(lym[1], lym_b), 40) if lym and lym_b and ctx.hour - lym[0] < 40 * H_PER_DAY else 0.0
    sign = "+" if excess >= 0 else "−"
    return [
        _driver(
            "Cumulative dose vs career limit",
            f"{to_fixed(dose, 0)} mSv · {to_fixed(cum_pct, 0)}%",
            cum_pct * 0.62,
            0.55,
            "radDose",
            "total dose is building toward the career limit",
        ),
        _driver(
            "Excess vs crew median",
            f"{sign}{to_fixed(abs(excess), 0)} mSv",
            excess * 1.4,
            0.25,
            "radDose",
            "dose is higher than the rest of the crew",
        ),
        _driver(
            "Dose rate, last 3 h",
            format_metric("doseRate", rate_now) if math.isfinite(rate_now) else "no data",
            (rate_now - 110) * 0.25,
            0.12,
            "doseRate",
            "radiation levels are elevated right now",
        ),
        _driver(
            "Lymphocytes, latest lab",
            format_metric("lymphocytes", lym[1]) if lym else "no data",
            lym_c,
            0.08,
            "lymphocytes",
            "immune cell count dipped after radiation exposure",
        ),
    ]


def _isolation(ctx: EngineContext, crew_id: str) -> list[Part]:
    missed = len(missed_check_in_days(ctx, crew_id, 7))
    return [
        _low_driver(ctx, crew_id, "mood", 7, "Mood, 7-day mean", 0.22, "mood has been lower than usual"),
        _high_driver(ctx, crew_id, "stress", 14, "Stress index, latest", 0.22, "reported stress has risen"),
        _low_driver(
            ctx,
            crew_id,
            "hrv",
            7,
            "HRV, 7-day resting mean",
            0.16,
            "the body shows signs of strain (lower heart rate variability)",
        ),
        _low_driver(
            ctx, crew_id, "sleepEfficiency", 7, "Sleep efficiency, 7 nights", 0.14, "sleep has been more broken"
        ),
        _high_driver(
            ctx, crew_id, "reactionTime", 10, "Reaction time, latest test", 0.11, "reaction time is slower", 30
        ),
        _driver(
            "Missed check-ins, 7 days", f"{missed} of 7", missed * 22, 0.15, None, "several daily check-ins were missed"
        ),
    ]


def _distance(ctx: EngineContext, crew_id: str) -> list[Part]:
    autonomous = ctx.link.mode == "autonomous"
    delay_c = 70.0 if autonomous else (ctx.link.delay_seconds / 60) * 4
    vision = symptom_count(recent_check_ins(ctx, crew_id, 7), "vision")
    kit_s = ctx.db.series(crew_id, "medKit").last_at(ctx.hour)
    kit = kit_s[1] if kit_s else 100.0
    return [
        _high_driver(ctx, crew_id, "workload", 14, "Workload index, latest", 0.32, "workload is heavy"),
        _high_driver(
            ctx,
            crew_id,
            "stress",
            14,
            "Stress under autonomy",
            0.16,
            "stress is up while decisions rest with the crew",
            25,
            60,
        ),
        _driver(
            "Earth link lost, autonomous" if autonomous else "Signal delay to Earth",
            "AUTONOMOUS" if autonomous else format_delay(ctx.link.delay_seconds),
            delay_c,
            0.22,
            None,
            "there is no link to Earth right now" if autonomous else "help from Earth takes several minutes each way",
        ),
        _driver(
            "Symptoms needing Earth consult",
            "Vision change reported" if vision else "None open",
            45 if vision else 0,
            0.15,
            None,
            "a symptom needs specialist advice from Earth",
        ),
        _driver(
            "Medical supply readiness",
            format_metric("medKit", kit),
            (92 - kit) * 2.2,
            0.15,
            "medKit",
            "medical supplies are running lower",
        ),
    ]


def _gravity_core(ctx: EngineContext, crew_id: str) -> list[Part]:
    bone_pct, bone_pm = loss_rate_per_month(ctx, crew_id, "boneDensity")
    lean_pct, lean_pm = loss_rate_per_month(ctx, crew_id, "muscleMass")
    str_pct, str_pm = loss_rate_per_month(ctx, crew_id, "legStrength")
    ci = recent_check_ins(ctx, crew_id, 7)
    h = symptom_count(ci, "headache")
    v = symptom_count(ci, "vision")
    cg = symptom_count(ci, "congestion")
    bp = symptom_count(ci, "back-pain")
    fluid = h * 12 + v * 35 + cg * 8
    return [
        _driver(
            "Bone density change",
            f"{format_pct(bone_pct, 1)} · {format_pct(bone_pm, 2)}/mo",
            (-bone_pm - 0.3) * 80,
            0.24,
            "boneDensity",
            "bone is thinning faster than the target",
        ),
        _driver(
            "Lean mass change",
            f"{format_pct(lean_pct, 1)} · {format_pct(lean_pm, 2)}/mo",
            (-lean_pm - 0.25) * 70,
            0.14,
            "muscleMass",
            "muscle mass is dropping",
        ),
        _driver(
            "Leg strength change",
            format_pct(str_pct, 1),
            (-str_pm - 0.35) * 55,
            0.1,
            "legStrength",
            "leg strength is declining",
        ),
        _driver(
            "Fluid-shift symptoms, 7 days",
            f"{h} headache · {v} vision · {cg} congestion",
            fluid,
            0.24,
            None,
            "headaches and vision changes suggest fluid shifting toward the head",
        ),
        _low_driver(ctx, crew_id, "visionAcuity", 10, "Near vision, latest check", 0.12, "near vision has changed", 45),
        _high_driver(ctx, crew_id, "bpSys", 7, "Systolic BP, 7-day resting mean", 0.08, "blood pressure has crept up"),
        _driver("Back pain reports, 7 days", f"{bp}", bp * 15, 0.08, None, "back pain has been reported"),
    ]


def _gravity(ctx: EngineContext, crew_id: str) -> list[Part]:
    """The frontend engine's gravity drivers, plus the Mobility & Balance Check once one has been done."""
    parts = _gravity_core(ctx, crew_id)
    result = mobility.assess(mobility.checks_until(ctx.db.mobility_checks(crew_id), ctx.hour))
    if result is None:
        return parts
    contribution = {"nominal": 0.0, "watch": 55.0, "alert": 85.0}[result.status]
    return [
        *parts,
        _driver(
            "Mobility & balance check",
            mobility.value_text(result),
            contribution,
            0.12,
            None,
            "balance, leg strength or knee bend has worsened",
        ),
    ]


def _environment(ctx: EngineContext, crew_id: str) -> list[Part]:
    co2 = recent_mean(ctx, crew_id, "co2", 3)
    ci = recent_check_ins(ctx, crew_id, 7)
    sym = symptom_count(ci, "headache") * 10 + symptom_count(ci, "congestion") * 10
    asleep = ctx.db.bundle(crew_id).asleep
    noise = ctx.db.series(crew_id, "cabinNoise").slice(ctx.hour - 3 * H_PER_DAY, ctx.hour)
    night = [v for t, v in noise.pairs() if 0 <= int(t) < len(asleep) and asleep[int(t)] > 0.5]
    night_noise = mean(night)
    wbc = ctx.db.series(crew_id, "wbc").last_at(ctx.hour)
    wbc_b = ctx.db.baseline(crew_id, "wbc")
    reports = sum(1 for c in ci if any(s in ("headache", "congestion") for s in c.symptoms))
    return [
        _driver(
            "CO₂ exposure, 3-day mean",
            format_metric("co2", co2) if math.isfinite(co2) else "no data",
            (co2 - 2.5) * 45,
            0.32,
            "co2",
            "CO₂ in the air has been high",
        ),
        _low_driver(
            ctx, crew_id, "sleepEfficiency", 7, "Sleep efficiency, 7 nights", 0.18, "sleep has been more broken", 25
        ),
        _driver(
            "Night-time noise, 3 nights",
            format_metric("cabinNoise", night_noise) if math.isfinite(night_noise) else "no data",
            (night_noise - 49) * 9,
            0.14,
            "cabinNoise",
            "the sleep area has been noisy at night",
        ),
        _low_driver(ctx, crew_id, "spo2", 3, "SpO₂, 3-day resting mean", 0.1, "blood oxygen is a little low"),
        _driver(
            "White blood cells, latest lab",
            format_metric("wbc", wbc[1]) if wbc else "no data",
            contrib(z_low(wbc[1], wbc_b), 40) if wbc and wbc_b else 0,
            0.1,
            "wbc",
            "the immune system looks suppressed",
        ),
        _driver(
            "Headache / congestion reports, 7 days",
            f"{reports}",
            sym,
            0.16,
            None,
            "headaches or congestion were reported",
        ),
    ]


_FNS: dict[str, Callable[[EngineContext, str], list[Part]]] = {
    "radiation": _radiation,
    "isolation": _isolation,
    "distance": _distance,
    "gravity": _gravity,
    "environment": _environment,
}

_CALM: dict[str, str] = {
    "radiation": "Dose is on the expected track for this point in the mission.",
    "isolation": "Mood, sleep and stress are in the usual range.",
    "distance": "Workload and support from Earth are manageable.",
    "gravity": "Bone, muscle and vision are holding up well with exercise.",
    "environment": "Air, noise and immune markers are in a healthy range.",
}

_NEXT_STEP: dict[str, str] = {
    "radiation": "Keep storm-shelter procedures fresh and limit time in lightly shielded modules.",
    "isolation": "Protected rest time and a private call home can help.",
    "distance": "Flag tasks that can wait and keep medical supplies under review.",
    "gravity": "Keep up daily exercise and report any change in vision or headaches.",
    "environment": "Report headaches; the life-support team is checking air and ventilation.",
}


def _fmt1(x: float) -> str:
    return to_fixed(x, 1) if math.isfinite(x) else "—"


def _headline(ctx: EngineContext, crew_id: str, hz: str) -> str:
    if hz == "radiation":
        dose = (latest(ctx, crew_id, "radDose") or (0, 0))[1]
        return f"{to_fixed(dose, 0)} mSv · {to_fixed((dose / ctx.career_limit_msv) * 100, 0)}% of career limit"
    if hz == "isolation":
        return f"Mood {_fmt1(recent_mean(ctx, crew_id, 'mood', 7))}/5 · sleep {_fmt1(recent_mean(ctx, crew_id, 'sleepDuration', 7))} h"
    if hz == "distance":
        w = ctx.db.series(crew_id, "workload").last_at(ctx.hour)
        delay = "No Earth link" if ctx.link.mode == "autonomous" else f"{format_delay(ctx.link.delay_seconds)} delay"
        return f"{delay} · workload {to_fixed(w[1], 0) if w else '—'}/100"
    if hz == "gravity":
        pct, _ = loss_rate_per_month(ctx, crew_id, "boneDensity")
        return f"Bone {format_pct(pct, 1)} since launch"
    return f"CO₂ {_fmt1(recent_mean(ctx, crew_id, 'co2', 2))} mmHg (48 h)"


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _explanation(hz: str, status: str, drivers: list[HazardDriver]) -> str:
    if status == "nominal":
        return _CALM[hz]
    concerns = [d.concern for d in drivers if d.concern and d.contribution >= 35][:2]
    if not concerns:
        return _CALM[hz]
    lead = f"{_cap(concerns[0])}, and {concerns[1]}." if len(concerns) == 2 else f"{_cap(concerns[0])}."
    return f"{lead} {_NEXT_STEP[hz]}"


def assess_hazards(ctx: EngineContext) -> list[HazardAssessment]:
    out: list[HazardAssessment] = []
    for a in ctx.db.crew():
        for hz in HAZARD_KEYS:
            parts = _FNS[hz](ctx, a.id)
            score = combine([(p.driver.contribution, p.w) for p in parts])
            status = score_to_status(score)
            drivers = sorted((p.driver for p in parts), key=lambda d: -d.contribution)
            out.append(
                HazardAssessment(
                    crew_id=a.id,
                    hazard=hz,
                    score=score,
                    status=status,
                    drivers=drivers,
                    headline=_headline(ctx, a.id, hz),
                    explanation=_explanation(hz, status, drivers),
                )
            )
    return out


def hazard_history(
    ctx: EngineContext, hazard: HazardKey, crew_id: str, from_day: int, to_day: int, step_days: int = 1
) -> list[Sample]:
    """Daily hazard score history for one crew member (for hazard trend charts)."""
    out: list[Sample] = []
    for d in range(from_day, to_day + 1, step_days):
        hour = min(ctx.hour, at(d, 20))
        parts = _FNS[hazard](ctx.at(hour), crew_id)
        out.append(Sample(t=hour, v=combine([(p.driver.contribution, p.w) for p in parts])))
    return out

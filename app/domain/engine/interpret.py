"""Plain-language reading of one metric for one astronaut (frontend `engine/interpret.ts`)."""

import math

from app.domain.engine.context import H_PER_DAY, EngineContext, half_band
from app.domain.engine.insights import detect_insights
from app.domain.format import format_metric, format_pct
from app.domain.metrics import HAZARD_COUNTERMEASURES, METRICS
from app.domain.prng import js_round
from app.domain.stats import mean, slope
from app.schemas.assessment import Evidence, MetricInterpretation, RecommendedAction

# Window used to judge "recent" per cadence (days).
_WINDOW = {"hourly": 7, "daily": 7, "session": 14, "weekly": 21, "monthly": 70}

_WHY: dict[str, str] = {
    "hr": "A resting heart rate that stays above normal can reflect stress, poor sleep, illness or deconditioning.",
    "hrv": "Heart rate variability falls when the body is under sustained stress or not recovering well.",
    "spo2": "Low blood oxygen can point to cabin air problems or a respiratory issue.",
    "coreTemp": "A rise in core temperature can be the first sign of infection or heat stress.",
    "bpSys": "In microgravity, fluid moves toward the head; rising pressure is linked to vision changes (SANS).",
    "bpDia": "Diastolic pressure helps judge cardiovascular adaptation to microgravity.",
    "resp": "Faster breathing at rest can signal anxiety, exertion or poor air quality.",
    "sleepDuration": "Short sleep builds up fatigue that slows reactions and raises the chance of mistakes.",
    "sleepEfficiency": "Broken sleep is less restorative even when time in bed looks normal.",
    "radDose": "Total dose drives long-term cancer and heart risk; staying under the career limit protects future health.",
    "doseRate": "A sudden rise means a solar particle event: shelter immediately to cut the dose.",
    "boneDensity": "Bone lost in space returns slowly and raises fracture risk on Mars and back on Earth.",
    "muscleMass": "Muscle loss reduces strength needed for spacewalks and work on the surface.",
    "legStrength": "Leg strength is what the crew needs to walk and work on Mars after months of weightlessness.",
    "mood": "Mood is the earliest self-reported sign of isolation stress.",
    "energy": "Low energy over several days often precedes illness or burnout.",
    "sleepQuality": "How rested someone feels is a direct check on sleep quality.",
    "stress": "Sustained stress affects sleep, team work and decision making.",
    "workload": "With growing signal delay, the crew plans more alone; sustained high workload erodes margin.",
    "co2": "CO₂ above 3 mmHg is linked to headaches, poor focus and worse sleep.",
    "reactionTime": "Slower reaction time is an objective sign of fatigue and affects safety-critical work.",
    "visionAcuity": "A drop in near vision can be an early sign of spaceflight-associated neuro-ocular syndrome.",
    "wbc": "Spaceflight can suppress the immune system; low counts raise infection risk.",
    "lymphocytes": "Lymphocytes are sensitive to radiation and stress.",
    "boneMarker": "A rising breakdown marker shows bone is being lost faster, weeks before a scan can see it.",
    "cabinNoise": "Noise disturbs sleep and, over time, hearing.",
    "cabinTemp": "Comfortable temperature supports sleep and reduces heat strain.",
    "cabinHumidity": "High humidity encourages microbial growth on surfaces.",
    "medKit": "With no resupply, medical supplies must last the whole mission.",
}

# Signals that compound almost everything: always worth checking alongside a vital.
_WELLNESS = ("sleepDuration", "sleepEfficiency", "hrv", "stress", "mood", "reactionTime")


def _related_out_of_range(ctx: EngineContext, crew_id: str, metric: str) -> list[Evidence]:
    """Related measurements currently outside this astronaut's normal range, most deviant first."""
    d = METRICS[metric]
    out: list[tuple[float, Evidence]] = []
    for k, m in METRICS.items():
        if k == metric or not (m.group == d.group or k in _WELLNESS):
            continue
        b = ctx.db.baseline(crew_id, k)
        if not b:
            continue
        series = ctx.db.series(crew_id, k)
        if m.cadence in ("hourly", "daily"):
            pairs = series.slice(ctx.hour - 7 * H_PER_DAY, ctx.hour).pairs()
            x = mean([v for t, v in pairs if m.cadence != "hourly" or not ctx.db.is_active(crew_id, t)])
        else:
            last = series.last_at(ctx.hour)
            x = last[1] if last else math.nan
        if not math.isfinite(x):
            continue
        z = (x - b.mean) / half_band(b)
        concerning = (z > 1 and m.concern != "low") or (z < -1 and m.concern != "high")
        if not concerning:
            continue
        out.append(
            (
                abs(z),
                Evidence(
                    label=m.label,
                    value=format_metric(k, x),
                    reference=format_metric(k, b.mean),
                    metric=k,
                    crew_id=crew_id,
                    direction="up" if z > 0 else "down",
                ),
            )
        )
    out.sort(key=lambda p: -p[0])
    return [e for _, e in out[:4]]


def interpret_metric(ctx: EngineContext, crew_id: str, metric: str) -> MetricInterpretation:
    d = METRICS[metric]
    a = ctx.db.astronaut(crew_id)
    name = a.name if a else crew_id
    days = _WINDOW.get(d.cadence, 7)
    series = ctx.db.series(crew_id, metric)
    recent = series.slice(ctx.hour - days * H_PER_DAY, ctx.hour)
    recent_pairs = recent.pairs()
    if d.cadence == "hourly" and metric != "doseRate" and d.group == "vitals":
        recent_pairs = [(t, v) for t, v in recent_pairs if not ctx.db.is_active(crew_id, t)]
    b = ctx.db.baseline(crew_id, metric)
    last = series.last_at(ctx.hour)
    avg = mean([v for _, v in recent_pairs]) if d.cadence in ("hourly", "daily") else (last[1] if last else math.nan)
    per_day = slope(series.slice(ctx.hour - max(days, 14) * H_PER_DAY, ctx.hour)) * H_PER_DAY
    fallback = abs(avg) * 0.05
    span = half_band(b) if b else (fallback if fallback and math.isfinite(fallback) else 1.0)
    trend = "flat" if abs(per_day * 7) < span * 0.25 else ("up" if per_day > 0 else "down")

    # Status vs baseline + thresholds
    status = "nominal"
    if b and math.isfinite(avg):
        out_low = avg < b.low and d.concern != "high"
        out_high = avg > b.high and d.concern != "low"
        if out_low or out_high:
            status = "watch"
    for t in d.thresholds:
        hit = avg > t.value if t.direction == "above" else avg < t.value
        if hit and (t.level == "alert" or status == "nominal"):
            status = t.level

    # What changed
    averaged = d.cadence in ("hourly", "daily")
    window_text = f"Over the last {days} days" if averaged else "At the latest measurement"
    verb = "averaged" if averaged else "was"
    summary = f"{window_text} {d.label.lower()} {verb} {format_metric(metric, avg)}"
    if b:
        pct = ((avg - b.mean) / b.mean) * 100
        where = "above" if avg > b.high else "below" if avg < b.low else "within"
        if where == "within":
            summary += f", within {name}'s normal range ({format_metric(metric, b.low, False)}–{format_metric(metric, b.high)})."
        else:
            summary += f", {format_pct(pct)} versus {name}'s normal ({format_metric(metric, b.mean)}), {where} the usual range."
    elif metric == "radDose":
        summary += f", {format_metric('radDose', avg / ctx.career_limit_msv * 100, False).split('.')[0]}% of the {int(ctx.career_limit_msv)} mSv career limit."
    else:
        summary += "."
    summary += (
        " The trend is stable." if trend == "flat" else f" The trend is {'rising' if trend == 'up' else 'falling'}."
    )

    # Related findings
    insights = [
        i
        for i in detect_insights(ctx)
        if (i.crew_id == crew_id or i.crew_id is None)
        and (
            i.primary_metric == metric
            or any(e.metric == metric and (e.crew_id or crew_id) == crew_id for e in i.evidence)
        )
    ]
    top = insights[0] if insights else None
    contributing = (
        [e for e in top.evidence if e.metric != metric][:4] if top else _related_out_of_range(ctx, crew_id, metric)
    )

    if top:
        recommended = top.recommended
    elif status == "nominal":
        recommended = [
            RecommendedAction(
                kind="acknowledge", label="No action needed", detail="Keep monitoring at the usual cadence."
            )
        ]
    else:
        recommended = [
            RecommendedAction(kind="message", label="Review countermeasure", detail=HAZARD_COUNTERMEASURES[h][0])
            for h in d.hazards[:1]
        ]

    samples = len(recent_pairs)
    confidence = (
        top.confidence if top else js_round(min(0.92, 0.55 + min(samples, 40) * 0.008 + (0.06 if b else 0)) * 100) / 100
    )

    return MetricInterpretation(
        crew_id=crew_id,
        metric=metric,
        summary=summary,
        why_it_matters=(top.why_it_matters if top else _WHY.get(metric, d.source)),
        contributing=contributing,
        confidence=confidence,
        recommended=recommended,
        trend=trend,
        status=status,
    )

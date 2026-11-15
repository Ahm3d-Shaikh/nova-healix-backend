"""Sleep debt, usually building ahead of an EVA."""

import math

from app.domain.engine.context import (
    H_PER_DAY,
    EngineContext,
    next_eva_for,
    recent_mean,
)
from app.domain.engine.insights.common import (
    confidence,
    direction_of,
    display_name,
    first_word,
    make_evidence,
)
from app.domain.format import format_metric, to_fixed
from app.schemas.assessment import Insight, RecommendedAction


def sleep_debt(ctx: EngineContext, crew_id: str) -> Insight | None:
    b = ctx.db.baseline(crew_id, "sleepDuration")
    x = recent_mean(ctx, crew_id, "sleepDuration", 5)
    if not b or not math.isfinite(x):
        return None
    deficit = b.mean - x
    if deficit < 1.0:
        return None

    eff_b = ctx.db.baseline(crew_id, "sleepEfficiency")
    eff = recent_mean(ctx, crew_id, "sleepEfficiency", 5)
    hrv_b = ctx.db.baseline(crew_id, "hrv")
    hrv = recent_mean(ctx, crew_id, "hrv", 7)
    sq = recent_mean(ctx, crew_id, "sleepQuality", 5)
    eva = next_eva_for(ctx, crew_id)
    eva_days = math.ceil((eva.start - ctx.hour) / H_PER_DAY) if eva else None
    eva_soon = eva_days is not None and eva_days <= 5
    shift = next(
        (
            e
            for e in ctx.db.events()
            if e.kind == "sleep-shift" and crew_id in e.crew_ids and e.start <= ctx.hour <= e.end
        ),
        None,
    )

    evidence = [
        make_evidence(
            "Sleep, 5-night mean",
            format_metric("sleepDuration", x),
            reference=format_metric("sleepDuration", b.mean),
            metric="sleepDuration",
            crew_id=crew_id,
            direction="down",
        )
    ]
    signals = 1
    if eff_b and eff < eff_b.low:
        signals += 1
        evidence.append(
            make_evidence(
                "Sleep efficiency, 5 nights",
                format_metric("sleepEfficiency", eff),
                reference=format_metric("sleepEfficiency", eff_b.mean),
                metric="sleepEfficiency",
                crew_id=crew_id,
                direction="down",
            )
        )
    if hrv_b and hrv < hrv_b.mean * 0.9:
        signals += 1
        evidence.append(
            make_evidence(
                "HRV, 7-day resting mean",
                format_metric("hrv", hrv),
                reference=format_metric("hrv", hrv_b.mean),
                metric="hrv",
                crew_id=crew_id,
                direction="down",
            )
        )
    if math.isfinite(sq):
        evidence.append(
            make_evidence(
                "Self-rated sleep quality",
                format_metric("sleepQuality", sq),
                metric="sleepQuality",
                crew_id=crew_id,
                direction=direction_of(sq, 3.5),
            )
        )
    rt_b = ctx.db.baseline(crew_id, "reactionTime")
    rt = ctx.db.series(crew_id, "reactionTime").last_at(ctx.hour)
    if rt_b and rt and rt[1] > rt_b.high:
        signals += 1
        evidence.append(
            make_evidence(
                "Reaction time, latest test",
                format_metric("reactionTime", rt[1]),
                reference=format_metric("reactionTime", rt_b.mean),
                metric="reactionTime",
                crew_id=crew_id,
                direction="up",
            )
        )
    if shift:
        evidence.append(make_evidence("Active schedule change", shift.label))
    if eva_soon and eva:
        evidence.append(make_evidence("Next EVA", f"{first_word(eva.label)} in {eva_days} d"))

    who = display_name(ctx, crew_id)
    title = f"Sleep debt building ahead of {first_word(eva.label)}" if eva_soon and eva else "Sleep debt building"
    severity = "alert" if deficit >= 2 or (eva_soon and deficit >= 1.8) else "watch"
    latest_sleep = ctx.db.series(crew_id, "sleepDuration").last_at(ctx.hour)
    recommended = [
        RecommendedAction(
            kind="countermeasure",
            countermeasure="sleep-shift",
            label="Adjust sleep shift",
            detail="Return sleep start to baseline for 2 nights; resume shift D144.",
        ),
        RecommendedAction(
            kind="countermeasure",
            countermeasure="rest",
            label="Protect sleep opportunity",
            detail="Block 8.5 h rest window; move evening procedure reviews.",
        ),
        RecommendedAction(
            kind="questionnaire",
            questionnaire_id="sleep",
            label="Assign sleep questionnaire",
            detail="Short sleep-quality questionnaire to confirm the cause.",
        ),
    ]
    if eva_soon:
        recommended.append(
            RecommendedAction(
                kind="escalate",
                label="Escalate EVA go/no-go input",
                detail="Flag to Earth flight surgeon for EVA readiness review.",
            )
        )
    return Insight(
        id=f"sleep-debt:{crew_id}",
        crew_id=crew_id,
        severity=severity,
        hazards=["isolation", "environment"],
        title=title,
        summary=(
            f"{who} has averaged {to_fixed(x, 1)} h of sleep over the last 5 nights, {to_fixed(deficit, 1)} h below personal baseline."
            + (" The decline started with the planned sleep shift." if shift else "")
            + (f" {first_word(eva.label)} is in {eva_days} days." if eva_soon and eva else "")
        ),
        why_it_matters=(
            "Accumulated sleep loss degrades reaction time, procedural memory and error detection. "
            + (
                "During EVA suit operations these errors carry the highest consequence on the mission."
                if eva_soon
                else "It also lowers mood and resilience to stress."
            )
        ),
        detected_at=latest_sleep[0] if latest_sleep else ctx.hour,
        primary_metric="sleepDuration",
        evidence=evidence,
        confidence=confidence(signals),
        recommended=recommended,
    )

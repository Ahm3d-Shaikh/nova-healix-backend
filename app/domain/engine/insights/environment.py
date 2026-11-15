"""Cabin CO2."""

from app.domain.engine.context import (
    EngineContext,
    recent_check_ins,
    recent_mean,
    symptom_count,
)
from app.domain.engine.insights.common import (
    display_name,
    make_evidence,
)
from app.domain.format import format_metric, to_fixed
from app.domain.mission_plan import hour_to_day
from app.domain.prng import js_round
from app.domain.stats import mean
from app.schemas.assessment import Insight, RecommendedAction


def cabin_co2(ctx: EngineContext) -> Insight | None:
    crew = ctx.db.crew()
    per = [(a.id, recent_mean(ctx, a.id, "co2", 2)) for a in crew]
    m = mean([v for _, v in per])
    if not m > 3:
        return None
    anomaly = next((e for e in ctx.db.events() if e.kind == "anomaly" and e.start <= ctx.hour <= e.end), None)
    hours = round_half_up(ctx.hour - anomaly.start) if anomaly else 48
    headaches = sum(symptom_count(recent_check_ins(ctx, a.id, 3), "headache") for a in crew)
    return Insight(
        id="co2:crew",
        crew_id=None,
        severity="alert" if m >= 4 else "watch",
        hazards=["environment"],
        title=f"Cabin CO₂ above 3 mmHg for {hours} h",
        summary=(
            f"Crew CO₂ exposure has averaged {to_fixed(m, 1)} mmHg over 48 h"
            + (f" ({anomaly.label}, D{hour_to_day(anomaly.start)})" if anomaly else "")
            + f". {headaches} headache reports across the crew in 3 days."
        ),
        why_it_matters="Chronic CO₂ above 3 mmHg is linked to headache, reduced cognitive performance and poorer sleep. All four crew are exposed.",
        detected_at=anomaly.start + 6 if anomaly else ctx.hour,
        primary_metric="co2",
        evidence=[
            make_evidence(
                f"{display_name(ctx, cid)}, 48 h mean",
                format_metric("co2", v),
                reference="3.0 mmHg limit",
                metric="co2",
                crew_id=cid,
                direction="up",
            )
            for cid, v in per
        ],
        confidence=0.9,
        recommended=[
            RecommendedAction(
                kind="message",
                label="Crew ventilation advisory",
                detail="Increase fan speed in crew quarters; avoid sleeping near the galley.",
            ),
            RecommendedAction(
                kind="escalate",
                label="ECLSS engineering support",
                detail="Send scrubber bed telemetry to the Earth ECLSS team.",
            ),
        ],
    )


def round_half_up(x: float) -> int:
    return int(js_round(x))


# -- crew mode ------------------------------------------------------------------------------------------

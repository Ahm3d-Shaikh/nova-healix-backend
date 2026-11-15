"""High workload."""

from app.domain.engine.context import (
    EngineContext,
    next_eva_for,
)
from app.domain.engine.insights.common import (
    display_name,
    first_word,
    make_evidence,
)
from app.domain.format import format_metric, to_fixed
from app.schemas.assessment import Insight, RecommendedAction


def workload_high(ctx: EngineContext, crew_id: str) -> Insight | None:
    b = ctx.db.baseline(crew_id, "workload")
    w = ctx.db.series(crew_id, "workload").last_at(ctx.hour)
    if not b or not w or w[1] < 65 or w[1] < b.high:
        return None
    who = display_name(ctx, crew_id)
    eva = next_eva_for(ctx, crew_id)
    return Insight(
        id=f"workload:{crew_id}",
        crew_id=crew_id,
        severity="info",
        hazards=["distance", "isolation"],
        title=f"Workload high during {first_word(eva.label)} prep" if eva else "Workload high",
        summary=f"{who} rated workload {to_fixed(w[1], 0)}/100 on the latest weekly questionnaire, above personal baseline ({to_fixed(b.mean, 0)}).",
        why_it_matters="With signal delay, the crew carries more of the planning load. Sustained high workload erodes sleep and margin.",
        detected_at=w[0],
        primary_metric="workload",
        evidence=[
            make_evidence(
                "Workload index",
                format_metric("workload", w[1]),
                reference=format_metric("workload", b.mean),
                metric="workload",
                crew_id=crew_id,
                direction="up",
            )
        ],
        confidence=0.74,
        recommended=[
            RecommendedAction(
                kind="message", label="Offer task re-plan", detail="Ask which tasks can move after the EVA."
            )
        ],
    )

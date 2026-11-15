"""Findings ("insights") from the shared data (frontend `engine/insights.ts`).

Rules fire per astronaut; crew-mode insights come from Nova safety flags (no transcript, by design),
notes the astronaut chose to share, and completed questionnaires.
"""

from app.domain.engine.context import EngineContext
from app.domain.engine.insights.checkin import check_in_flag
from app.domain.engine.insights.common import SAFETY_SIGNAL_LABEL, SEVERITY_RANK, SYMPTOM_LABEL, Rule
from app.domain.engine.insights.crew_mode import crew_mode_insights
from app.domain.engine.insights.environment import cabin_co2
from app.domain.engine.insights.gravity import bone_on_track, exercise_compliance, fluid_shift
from app.domain.engine.insights.isolation import isolation_stress, loneliness_flag
from app.domain.engine.insights.mobility import mobility_flag
from app.domain.engine.insights.radiation import radiation_outlier
from app.domain.engine.insights.sleep import sleep_debt
from app.domain.engine.insights.workload import workload_high
from app.schemas.assessment import Insight

__all__ = ["SAFETY_SIGNAL_LABEL", "SEVERITY_RANK", "SYMPTOM_LABEL", "detect_insights"]

# Order matters only for ties: findings are sorted by urgency, severity and recency below.
RULES: list[Rule] = [
    sleep_debt,
    isolation_stress,
    loneliness_flag,
    radiation_outlier,
    fluid_shift,
    exercise_compliance,
    bone_on_track,
    workload_high,
    check_in_flag,
    mobility_flag,
]


def detect_insights(ctx: EngineContext) -> list[Insight]:
    out: list[Insight] = []
    for a in ctx.db.crew():
        for rule in RULES:
            i = rule(ctx, a.id)
            if i:
                out.append(i)
    co2 = cabin_co2(ctx)
    if co2:
        out.append(co2)
    out += crew_mode_insights(ctx)
    # Nova safety alerts always come first: someone needs help now.
    return sorted(
        out, key=lambda i: (0 if i.id.startswith("safety:") else 1, -SEVERITY_RANK[i.severity], -i.detected_at)
    )

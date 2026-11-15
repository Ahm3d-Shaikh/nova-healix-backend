"""A daily check-in that flags something new."""

from app.domain.engine.context import (
    EngineContext,
    recent_check_ins,
)
from app.domain.engine.insights.common import (
    SYMPTOM_LABEL,
    display_name,
    make_evidence,
)
from app.schemas.assessment import Insight, RecommendedAction


def check_in_flag(ctx: EngineContext, crew_id: str) -> Insight | None:
    """The latest check-in flags anything new (mood <= 2 or a non-fluid-shift symptom) within 24 h."""
    recent = recent_check_ins(ctx, crew_id, 1)
    if not recent:
        return None
    c = recent[-1]
    flagged = [s for s in c.symptoms if s in ("nausea", "other", "back-pain")]
    low_mood = c.mood <= 2
    if not flagged and not low_mood:
        return None
    who = display_name(ctx, crew_id)
    parts = [*(SYMPTOM_LABEL[s].lower() for s in flagged), *([f"mood {c.mood}/5"] if low_mood else [])]
    evidence = [
        make_evidence("Mood", f"{c.mood}/5", metric="mood", crew_id=crew_id),
        make_evidence("Energy", f"{c.energy}/5", metric="energy", crew_id=crew_id),
        make_evidence("Sleep quality", f"{c.sleep_quality}/5", metric="sleepQuality", crew_id=crew_id),
    ]
    if c.symptoms:
        evidence.append(make_evidence("Symptoms", ", ".join(SYMPTOM_LABEL[s] for s in c.symptoms)))
    return Insight(
        id=f"checkin:{crew_id}:{c.day}",
        crew_id=crew_id,
        severity="watch" if low_mood or "nausea" in flagged else "info",
        hazards=["gravity"] if "back-pain" in flagged else ["isolation"],
        title=f"Check-in flag: {', '.join(parts)}",
        summary=f"{who}'s D{c.day} check-in reports {' and '.join(parts)}." + (f' Note: "{c.note}"' if c.note else ""),
        why_it_matters="Self-reports are the earliest signal for symptoms wearables cannot see.",
        detected_at=c.at,
        primary_metric="mood",
        evidence=evidence,
        confidence=0.7,
        recommended=[
            RecommendedAction(kind="message", label="Follow up", detail="Ask for details at the next convenient break.")
        ],
    )

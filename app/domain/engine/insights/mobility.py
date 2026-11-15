"""Mobility & Balance Check: a finding when the latest check is flagged."""

from app.domain import mobility
from app.domain.engine.context import (
    EngineContext,
)
from app.domain.engine.insights.common import (
    display_name,
    make_evidence,
)
from app.schemas.assessment import Evidence, Insight, RecommendedAction


def mobility_flag(ctx: EngineContext, crew_id: str) -> Insight | None:
    """Mobility & Balance Check: a finding when the latest reliable check is flagged."""
    result = mobility.assess(mobility.checks_until(ctx.db.mobility_checks(crew_id), ctx.hour))
    if result is None or result.status == "nominal":
        return None
    who = display_name(ctx, crew_id)
    flagged = [t for t in result.tests if t.status != "nominal"]
    evidence: list[Evidence] = []
    for t in result.tests:
        base = mobility.test_text(t, t.baseline) if t.baseline else None
        evidence.append(
            make_evidence(
                t.label,
                mobility.test_text(t, t.values),
                reference=f"{base} at first check" if base else None,
                crew_id=crew_id,
                direction=("up" if t.test == "sit_to_stand" else "down") if t.status != "nominal" else None,
            )
        )
    evidence.append(make_evidence("Checks used", f"{result.checks_used}"))
    recommended = [
        RecommendedAction(
            kind="message",
            label="Ask for a repeat check",
            detail="Repeat the Mobility & Balance Check tomorrow, side-on to the camera in good light.",
        ),
        RecommendedAction(
            kind="countermeasure",
            countermeasure="exercise",
            label="Review resistive exercise",
            detail="Check that the resistive exercise protocol is being done in full.",
        ),
    ]
    if result.status == "alert":
        recommended.append(
            RecommendedAction(
                kind="escalate",
                label="Flag for flight surgeon review",
                detail="Clearly reduced balance, leg strength or knee bend: request an in-person assessment.",
            )
        )
    return Insight(
        id=f"mobility:{crew_id}",
        crew_id=crew_id,
        severity=result.status,
        hazards=["gravity"],
        title=f"Mobility & balance check flagged: {', '.join(t.label.lower() for t in flagged)}",
        summary=(
            f"{who}'s Mobility & Balance Check on D{result.last_check_day} flagged {', '.join(t.label.lower() for t in flagged)}"
            + (" compared with the first check." if result.checks_used > 1 else ".")
        ),
        why_it_matters=(
            "Slower balance control, a slower sit-to-stand or a shallower squat can be early signs of muscle and joint "
            "deconditioning in reduced gravity. This check looks at movement only, not bone health."
        ),
        detected_at=result.last_check_at,
        primary_metric="legStrength",
        evidence=evidence,
        confidence=0.8 if result.checks_used > 1 else 0.7,
        recommended=recommended,
    )

"""Cumulative radiation dose outlier."""

from app.domain.engine.context import (
    EngineContext,
    latest,
)
from app.domain.engine.insights.common import (
    display_name,
    make_evidence,
)
from app.domain.format import to_fixed
from app.domain.mission_plan import hour_to_day
from app.schemas.assessment import Insight, RecommendedAction


def radiation_outlier(ctx: EngineContext, crew_id: str) -> Insight | None:
    dose = (latest(ctx, crew_id, "radDose") or (0, 0))[1]
    doses = sorted((latest(ctx, a.id, "radDose") or (0, 0))[1] for a in ctx.db.crew())
    median = (doses[1] + doses[2]) / 2
    if dose < median * 1.08 or dose < max(doses) - 1e-6:
        return None
    pct = (dose / ctx.career_limit_msv) * 100
    day = hour_to_day(ctx.hour)
    remaining = max(0, 260 - day)
    projected = dose + remaining * 1.8
    who = display_name(ctx, crew_id)
    spe = next((e for e in ctx.db.events() if e.kind == "spe" and e.start <= ctx.hour), None)
    evidence = [
        make_evidence(
            "Cumulative effective dose",
            f"{to_fixed(dose, 0)} mSv",
            reference=f"{to_fixed(median, 0)} mSv crew median",
            metric="radDose",
            crew_id=crew_id,
            direction="up",
        ),
        make_evidence(
            "Share of career limit", f"{to_fixed(pct, 0)}%", reference=f"{to_fixed(ctx.career_limit_msv, 0)} mSv limit"
        ),
        make_evidence("Projected at arrival", f"{to_fixed(projected, 0)} mSv"),
    ]
    if spe:
        evidence.append(make_evidence("Contributing event", spe.label))
    return Insight(
        id=f"rad-outlier:{crew_id}",
        crew_id=crew_id,
        severity="watch",
        hazards=["radiation"],
        title="Highest cumulative radiation dose on crew",
        summary=(
            f"{who} is at {to_fixed(dose, 0)} mSv ({to_fixed(pct, 0)}% of career limit), {to_fixed(dose - median, 0)} mSv above the "
            "crew median. Most of the gap comes from late storm-shelter entry during the D97 solar particle event."
        ),
        why_it_matters=(
            f"At the current GCR rate {who} reaches about {to_fixed(projected, 0)} mSv at Mars arrival "
            f"({to_fixed((projected / ctx.career_limit_msv) * 100, 0)}% of career limit), leaving little margin for another solar particle event."
        ),
        detected_at=spe.end if spe else ctx.hour,
        primary_metric="radDose",
        evidence=evidence,
        confidence=0.92,
        recommended=[
            RecommendedAction(
                kind="countermeasure",
                countermeasure="storm-shelter",
                label="Pre-assign shelter role",
                detail="Make another crew member responsible for the medical bay during the next SPE so this astronaut shelters first.",
            ),
            RecommendedAction(
                kind="message", label="Review duty cycle", detail="Reduce scheduled time in low-shielding modules."
            ),
            RecommendedAction(
                kind="escalate",
                label="Career dose review",
                detail="Send dosimetry summary to the Earth radiation health officer.",
            ),
        ],
    )

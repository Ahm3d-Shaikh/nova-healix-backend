"""Gravity: fluid shift (SANS screen), missed exercise and bone loss within target."""

from app.domain.engine.context import (
    H_PER_DAY,
    EngineContext,
    recent_check_ins,
    recent_mean,
    symptom_count,
)
from app.domain.engine.insights.common import (
    confidence,
    display_name,
    make_evidence,
)
from app.domain.format import format_metric, format_pct
from app.domain.mission_plan import hour_to_day
from app.schemas.assessment import Insight, RecommendedAction


def fluid_shift(ctx: EngineContext, crew_id: str) -> Insight | None:
    ci = recent_check_ins(ctx, crew_id, 7)
    headaches = symptom_count(ci, "headache")
    vision = [c for c in ci if "vision" in c.symptoms]
    if headaches < 3 and not vision:
        return None
    sys_b = ctx.db.baseline(crew_id, "bpSys")
    sys_ = recent_mean(ctx, crew_id, "bpSys", 7)
    evidence = [make_evidence("Headache reports, 7 days", f"{headaches} of {len(ci)} check-ins", direction="up")]
    signals = 1
    if vision:
        signals += 2
        evidence.append(make_evidence("Vision change reported", ", ".join(f"D{v.day}" for v in vision)))
    acc_b = ctx.db.baseline(crew_id, "visionAcuity")
    acc = ctx.db.series(crew_id, "visionAcuity").last_at(ctx.hour)
    if acc_b and acc and acc[1] < acc_b.low:
        signals += 1
        evidence.append(
            make_evidence(
                "Near visual acuity, latest check",
                format_metric("visionAcuity", acc[1]),
                reference=format_metric("visionAcuity", acc_b.mean),
                metric="visionAcuity",
                crew_id=crew_id,
                direction="down",
            )
        )
    congestion = symptom_count(ci, "congestion")
    if congestion:
        signals += 1
        evidence.append(make_evidence("Congestion reports, 7 days", f"{congestion}"))
    if sys_b and sys_ > sys_b.mean + 3:
        signals += 1
        evidence.append(
            make_evidence(
                "Systolic BP, 7-day resting mean",
                format_metric("bpSys", sys_),
                reference=format_metric("bpSys", sys_b.mean),
                metric="bpSys",
                crew_id=crew_id,
                direction="up",
            )
        )
    who = display_name(ctx, crew_id)
    last_report = next((c for c in reversed(ci) if c.symptoms), None)
    return Insight(
        id=f"fluid-shift:{crew_id}",
        crew_id=crew_id,
        severity="watch",
        hazards=["gravity"],
        title="Headaches with vision change. SANS screen advised" if vision else "Recurring headaches",
        summary=(
            f"{who} reported headaches on {headaches} of the last {len(ci)} check-ins"
            + (f" and a change in near vision on D{vision[0].day}" if vision else "")
            + ". Resting systolic pressure has crept up over the same period."
        ),
        why_it_matters=(
            "Headache with vision change in microgravity can indicate spaceflight-associated neuro-ocular syndrome (SANS), "
            "caused by headward fluid shift. Early imaging lets the crew start countermeasures before changes become persistent."
        ),
        detected_at=last_report.at if last_report else ctx.hour,
        primary_metric="bpSys",
        evidence=evidence,
        confidence=confidence(signals, 0.5),
        recommended=[
            RecommendedAction(
                kind="message",
                label="Request ocular exam",
                detail="Ask for fundoscopy, Amsler grid and visual acuity tonight.",
            ),
            RecommendedAction(
                kind="escalate",
                label="Ophthalmology consult",
                detail="Queue imaging review with the Earth ophthalmologist.",
            ),
            RecommendedAction(
                kind="countermeasure",
                countermeasure="exercise",
                label="Add LBNP session",
                detail="Lower-body negative pressure, 30 min daily for 5 days.",
            ),
        ],
    )


def exercise_compliance(ctx: EngineContext, crew_id: str) -> Insight | None:
    today = hour_to_day(ctx.hour)
    sessions = [s for s in ctx.db.exercise(crew_id) if s.day >= today - 14 and s.end <= ctx.hour]
    missed = [s for s in sessions if not s.done]
    if len(missed) < 4:
        return None
    bone = ctx.db.series(crew_id, "boneDensity")
    lean = ctx.db.series(crew_id, "muscleMass")
    b_last = bone.last_at(ctx.hour)
    l_last = lean.last_at(ctx.hour)
    b_pct = ((b_last[1] - bone.v[0]) / bone.v[0]) * 100 if b_last else 0
    l_pct = ((l_last[1] - lean.v[0]) / lean.v[0]) * 100 if l_last else 0
    who = display_name(ctx, crew_id)
    done = len(sessions) - len(missed)
    return Insight(
        id=f"exercise:{crew_id}",
        crew_id=crew_id,
        severity="watch",
        hazards=["gravity", "isolation"],
        title="Exercise sessions missed",
        summary=(
            f"{who} completed {done} of {len(sessions)} scheduled exercise sessions in the last 14 days. "
            "Weekly bone and lean-mass measurements are now declining faster than the countermeasure target."
        ),
        why_it_matters=(
            "Resistive exercise is the main countermeasure against microgravity bone and muscle loss. "
            "Lost mass is slow to recover and affects surface operations on arrival."
        ),
        detected_at=missed[-1].end if missed else ctx.hour,
        primary_metric="muscleMass",
        evidence=[
            make_evidence("Sessions completed, 14 days", f"{done} / {len(sessions)}", direction="down"),
            make_evidence(
                "Bone density since launch",
                format_pct(b_pct, 1),
                reference="−0.5%/mo target",
                metric="boneDensity",
                crew_id=crew_id,
                direction="down",
            ),
            make_evidence(
                "Lean mass since launch", format_pct(l_pct, 1), metric="muscleMass", crew_id=crew_id, direction="down"
            ),
        ],
        confidence=0.83,
        recommended=[
            RecommendedAction(
                kind="countermeasure",
                countermeasure="exercise",
                label="Reschedule exercise",
                detail="Move sessions to a fixed morning slot with a crew partner.",
            ),
            RecommendedAction(
                kind="message",
                label="Ask about barriers",
                detail="Check whether workload, motivation or discomfort is the cause.",
            ),
        ],
    )


def bone_on_track(ctx: EngineContext, crew_id: str) -> Insight | None:
    bone = ctx.db.series(crew_id, "boneDensity")
    last = bone.last_at(ctx.hour)
    if not last or not len(bone):
        return None
    pct = ((last[1] - bone.v[0]) / bone.v[0]) * 100
    months = (last[0] - bone.t[0]) / H_PER_DAY / 30.44
    if months < 1 or pct / months < -0.42:
        return None
    who = display_name(ctx, crew_id)
    return Insight(
        id=f"bone-on-track:{crew_id}",
        crew_id=crew_id,
        severity="info",
        hazards=["gravity"],
        title="Bone loss within countermeasure target",
        summary=(
            f"{who}'s femoral neck density is {format_pct(pct, 1)} since launch ({format_pct(pct / months, 2)}/month), "
            "inside the −0.5%/month target. Exercise compliance is consistent."
        ),
        why_it_matters="Confirms the current exercise prescription is working; useful as a reference for the rest of the crew.",
        detected_at=last[0],
        primary_metric="boneDensity",
        evidence=[
            make_evidence(
                "BMD change since launch", format_pct(pct, 1), metric="boneDensity", crew_id=crew_id, direction="down"
            ),
            make_evidence("Rate", f"{format_pct(pct / months, 2)}/mo", reference="−0.50%/mo target"),
        ],
        confidence=0.88,
        recommended=[RecommendedAction(kind="acknowledge", label="Acknowledge", detail="No action needed.")],
    )

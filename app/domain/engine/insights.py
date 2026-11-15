"""Findings ("insights") from the shared data (frontend `engine/insights.ts`).

Rules fire per astronaut; crew-mode insights come from Nova safety flags (no transcript, by design),
notes the astronaut chose to share, and completed questionnaires.
"""

import math
from collections.abc import Callable

from app.domain.engine.context import (
    H_PER_DAY,
    EngineContext,
    latest,
    missed_check_in_days,
    next_eva_for,
    recent_check_ins,
    recent_mean,
    symptom_count,
)
from app.domain.format import format_clock, format_delay, format_metric, format_mission_time, format_pct, to_fixed
from app.domain.mission_plan import FLIGHT_DIRECTOR, hour_to_day
from app.domain.prng import clamp, js_round
from app.domain.questionnaires import QUESTIONNAIRES
from app.domain.stats import mean
from app.domain.store import SafetyFlag
from app.schemas.assessment import Evidence, Insight, RecommendedAction

SEVERITY_RANK = {"info": 0, "watch": 1, "alert": 2}
SYMPTOM_LABEL = {
    "headache": "Headache",
    "nausea": "Nausea",
    "vision": "Vision change",
    "back-pain": "Back pain",
    "congestion": "Congestion",
    "other": "Other",
}
SAFETY_SIGNAL_LABEL = {
    "wish-to-die": "expressed a wish to die",
    "suicidal-thoughts": "expressed suicidal thoughts",
    "self-harm-intent": "expressed intent to harm themself",
    "confirmed-when-asked": "said yes when Nova asked about thoughts of self-harm",
    "chest-pain": "reported chest pain",
    "breathing": "reported difficulty breathing",
    "stroke-signs": "reported stroke-like symptoms (numbness or slurred speech)",
    "unconscious": "reported fainting or blacking out",
    "vision-loss": "reported sudden loss of vision",
    "severe-headache": "reported a sudden severe headache",
    "seizure": "reported a seizure",
}

Rule = Callable[[EngineContext, str], Insight | None]


def _confidence(signals: int, base: float = 0.56) -> float:
    return js_round(clamp(base + signals * 0.08, 0, 0.95) * 100) / 100


def _name(ctx: EngineContext, crew_id: str) -> str:
    a = ctx.db.astronaut(crew_id)
    return a.name if a else crew_id


def _dir(now: float, ref: float) -> str:
    return "flat" if abs(now - ref) < 1e-6 else ("up" if now > ref else "down")


def _ev(label: str, value: str, **kw: object) -> Evidence:
    return Evidence(label=label, value=value, **kw)


def _short(label: str) -> str:
    return label.split(" ", maxsplit=1)[0]


# -- rules ------------------------------------------------------------------------------------------
def _sleep_debt(ctx: EngineContext, crew_id: str) -> Insight | None:
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
        _ev(
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
            _ev(
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
            _ev(
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
            _ev(
                "Self-rated sleep quality",
                format_metric("sleepQuality", sq),
                metric="sleepQuality",
                crew_id=crew_id,
                direction=_dir(sq, 3.5),
            )
        )
    rt_b = ctx.db.baseline(crew_id, "reactionTime")
    rt = ctx.db.series(crew_id, "reactionTime").last_at(ctx.hour)
    if rt_b and rt and rt[1] > rt_b.high:
        signals += 1
        evidence.append(
            _ev(
                "Reaction time, latest test",
                format_metric("reactionTime", rt[1]),
                reference=format_metric("reactionTime", rt_b.mean),
                metric="reactionTime",
                crew_id=crew_id,
                direction="up",
            )
        )
    if shift:
        evidence.append(_ev("Active schedule change", shift.label))
    if eva_soon and eva:
        evidence.append(_ev("Next EVA", f"{_short(eva.label)} in {eva_days} d"))

    who = _name(ctx, crew_id)
    title = f"Sleep debt building ahead of {_short(eva.label)}" if eva_soon and eva else "Sleep debt building"
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
            + (f" {_short(eva.label)} is in {eva_days} days." if eva_soon and eva else "")
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
        confidence=_confidence(signals),
        recommended=recommended,
    )


def _isolation_stress(ctx: EngineContext, crew_id: str) -> Insight | None:
    evidence: list[Evidence] = []
    signals = 0
    mood_b = ctx.db.baseline(crew_id, "mood")
    mood = recent_mean(ctx, crew_id, "mood", 7)
    if mood_b and mood < mood_b.low:
        signals += 1
        evidence.append(
            _ev(
                "Mood, 7-day mean",
                format_metric("mood", mood),
                reference=format_metric("mood", mood_b.mean),
                metric="mood",
                crew_id=crew_id,
                direction="down",
            )
        )
    stress_b = ctx.db.baseline(crew_id, "stress")
    stress_all = ctx.db.series(crew_id, "stress").slice(0, ctx.hour).pairs()
    stress = stress_all[-1] if stress_all else None
    stress_3w = stress_all[-4] if len(stress_all) >= 4 else None
    if stress_b and stress and stress[1] > stress_b.high:
        signals += 1
        evidence.append(
            _ev(
                "Stress index, latest weekly",
                format_metric("stress", stress[1]),
                reference=f"{format_metric('stress', stress_3w[1])} 3 wk ago"
                if stress_3w
                else format_metric("stress", stress_b.mean),
                metric="stress",
                crew_id=crew_id,
                direction="up",
            )
        )
    hrv_b = ctx.db.baseline(crew_id, "hrv")
    hrv = recent_mean(ctx, crew_id, "hrv", 7)
    if hrv_b and hrv < hrv_b.mean * 0.85:
        signals += 1
        evidence.append(
            _ev(
                "HRV, 7-day resting mean",
                f"{format_metric('hrv', hrv)} ({format_pct(((hrv - hrv_b.mean) / hrv_b.mean) * 100)})",
                reference=format_metric("hrv", hrv_b.mean),
                metric="hrv",
                crew_id=crew_id,
                direction="down",
            )
        )
    missed = missed_check_in_days(ctx, crew_id, 10)
    if len(missed) >= 2:
        signals += 1
        evidence.append(
            _ev("Missed check-ins, 10 days", f"{len(missed)} ({', '.join(f'D{d}' for d in missed)})", direction="up")
        )
    eff_b = ctx.db.baseline(crew_id, "sleepEfficiency")
    eff = recent_mean(ctx, crew_id, "sleepEfficiency", 7)
    if eff_b and eff < eff_b.low:
        signals += 1
        evidence.append(
            _ev(
                "Sleep efficiency, 7 nights",
                format_metric("sleepEfficiency", eff),
                reference=format_metric("sleepEfficiency", eff_b.mean),
                metric="sleepEfficiency",
                crew_id=crew_id,
                direction="down",
            )
        )
    if signals < 3:
        return None
    who = _name(ctx, crew_id)
    mood_latest = latest(ctx, crew_id, "mood")
    return Insight(
        id=f"isolation-stress:{crew_id}",
        crew_id=crew_id,
        severity="alert" if signals >= 4 else "watch",
        hazards=["isolation", "distance"],
        title="Isolation stress rising",
        summary=(
            f"{signals} independent signals for {who} point the same way: lower mood, higher reported stress, "
            f"suppressed HRV and fewer check-ins. The trend started around D{hour_to_day(ctx.hour) - 30} and has not levelled off."
        ),
        why_it_matters=(
            "Sustained isolation stress is a leading indicator for sleep disruption, conflict within the crew and reduced "
            "performance. With growing signal delay, early intervention onboard matters more."
        ),
        detected_at=max(stress[0] if stress else 0, mood_latest[0] if mood_latest else 0),
        primary_metric="stress",
        evidence=evidence,
        confidence=_confidence(signals, 0.5),
        recommended=[
            RecommendedAction(
                kind="message",
                label="Check in privately",
                detail="Send a private, low-pressure message from the flight surgeon.",
            ),
            RecommendedAction(
                kind="questionnaire",
                questionnaire_id="team",
                label="Assign team dynamics questionnaire",
                detail="Short isolation and team-dynamics questionnaire.",
            ),
            RecommendedAction(
                kind="countermeasure",
                countermeasure="rest",
                label="Protected off-duty block",
                detail="Schedule 2 h crew-choice time tomorrow.",
            ),
            RecommendedAction(
                kind="escalate",
                label="Request psych conference",
                detail="Queue a private conference with the Earth-based psychologist.",
            ),
        ],
    )


def _radiation_outlier(ctx: EngineContext, crew_id: str) -> Insight | None:
    dose = (latest(ctx, crew_id, "radDose") or (0, 0))[1]
    doses = sorted((latest(ctx, a.id, "radDose") or (0, 0))[1] for a in ctx.db.crew())
    median = (doses[1] + doses[2]) / 2
    if dose < median * 1.08 or dose < max(doses) - 1e-6:
        return None
    pct = (dose / ctx.career_limit_msv) * 100
    day = hour_to_day(ctx.hour)
    remaining = max(0, 260 - day)
    projected = dose + remaining * 1.8
    who = _name(ctx, crew_id)
    spe = next((e for e in ctx.db.events() if e.kind == "spe" and e.start <= ctx.hour), None)
    evidence = [
        _ev(
            "Cumulative effective dose",
            f"{to_fixed(dose, 0)} mSv",
            reference=f"{to_fixed(median, 0)} mSv crew median",
            metric="radDose",
            crew_id=crew_id,
            direction="up",
        ),
        _ev(
            "Share of career limit", f"{to_fixed(pct, 0)}%", reference=f"{to_fixed(ctx.career_limit_msv, 0)} mSv limit"
        ),
        _ev("Projected at arrival", f"{to_fixed(projected, 0)} mSv"),
    ]
    if spe:
        evidence.append(_ev("Contributing event", spe.label))
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


def _fluid_shift(ctx: EngineContext, crew_id: str) -> Insight | None:
    ci = recent_check_ins(ctx, crew_id, 7)
    headaches = symptom_count(ci, "headache")
    vision = [c for c in ci if "vision" in c.symptoms]
    if headaches < 3 and not vision:
        return None
    sys_b = ctx.db.baseline(crew_id, "bpSys")
    sys_ = recent_mean(ctx, crew_id, "bpSys", 7)
    evidence = [_ev("Headache reports, 7 days", f"{headaches} of {len(ci)} check-ins", direction="up")]
    signals = 1
    if vision:
        signals += 2
        evidence.append(_ev("Vision change reported", ", ".join(f"D{v.day}" for v in vision)))
    acc_b = ctx.db.baseline(crew_id, "visionAcuity")
    acc = ctx.db.series(crew_id, "visionAcuity").last_at(ctx.hour)
    if acc_b and acc and acc[1] < acc_b.low:
        signals += 1
        evidence.append(
            _ev(
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
        evidence.append(_ev("Congestion reports, 7 days", f"{congestion}"))
    if sys_b and sys_ > sys_b.mean + 3:
        signals += 1
        evidence.append(
            _ev(
                "Systolic BP, 7-day resting mean",
                format_metric("bpSys", sys_),
                reference=format_metric("bpSys", sys_b.mean),
                metric="bpSys",
                crew_id=crew_id,
                direction="up",
            )
        )
    who = _name(ctx, crew_id)
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
        confidence=_confidence(signals, 0.5),
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


def _exercise_compliance(ctx: EngineContext, crew_id: str) -> Insight | None:
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
    who = _name(ctx, crew_id)
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
            _ev("Sessions completed, 14 days", f"{done} / {len(sessions)}", direction="down"),
            _ev(
                "Bone density since launch",
                format_pct(b_pct, 1),
                reference="−0.5%/mo target",
                metric="boneDensity",
                crew_id=crew_id,
                direction="down",
            ),
            _ev("Lean mass since launch", format_pct(l_pct, 1), metric="muscleMass", crew_id=crew_id, direction="down"),
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


def _bone_on_track(ctx: EngineContext, crew_id: str) -> Insight | None:
    bone = ctx.db.series(crew_id, "boneDensity")
    last = bone.last_at(ctx.hour)
    if not last or not len(bone):
        return None
    pct = ((last[1] - bone.v[0]) / bone.v[0]) * 100
    months = (last[0] - bone.t[0]) / H_PER_DAY / 30.44
    if months < 1 or pct / months < -0.42:
        return None
    who = _name(ctx, crew_id)
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
            _ev("BMD change since launch", format_pct(pct, 1), metric="boneDensity", crew_id=crew_id, direction="down"),
            _ev("Rate", f"{format_pct(pct / months, 2)}/mo", reference="−0.50%/mo target"),
        ],
        confidence=0.88,
        recommended=[RecommendedAction(kind="acknowledge", label="Acknowledge", detail="No action needed.")],
    )


def _workload_high(ctx: EngineContext, crew_id: str) -> Insight | None:
    b = ctx.db.baseline(crew_id, "workload")
    w = ctx.db.series(crew_id, "workload").last_at(ctx.hour)
    if not b or not w or w[1] < 65 or w[1] < b.high:
        return None
    who = _name(ctx, crew_id)
    eva = next_eva_for(ctx, crew_id)
    return Insight(
        id=f"workload:{crew_id}",
        crew_id=crew_id,
        severity="info",
        hazards=["distance", "isolation"],
        title=f"Workload high during {_short(eva.label)} prep" if eva else "Workload high",
        summary=f"{who} rated workload {to_fixed(w[1], 0)}/100 on the latest weekly questionnaire, above personal baseline ({to_fixed(b.mean, 0)}).",
        why_it_matters="With signal delay, the crew carries more of the planning load. Sustained high workload erodes sleep and margin.",
        detected_at=w[0],
        primary_metric="workload",
        evidence=[
            _ev(
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


def _check_in_flag(ctx: EngineContext, crew_id: str) -> Insight | None:
    """The latest check-in flags anything new (mood <= 2 or a non-fluid-shift symptom) within 24 h."""
    recent = recent_check_ins(ctx, crew_id, 1)
    if not recent:
        return None
    c = recent[-1]
    flagged = [s for s in c.symptoms if s in ("nausea", "other", "back-pain")]
    low_mood = c.mood <= 2
    if not flagged and not low_mood:
        return None
    who = _name(ctx, crew_id)
    parts = [*(SYMPTOM_LABEL[s].lower() for s in flagged), *([f"mood {c.mood}/5"] if low_mood else [])]
    evidence = [
        _ev("Mood", f"{c.mood}/5", metric="mood", crew_id=crew_id),
        _ev("Energy", f"{c.energy}/5", metric="energy", crew_id=crew_id),
        _ev("Sleep quality", f"{c.sleep_quality}/5", metric="sleepQuality", crew_id=crew_id),
    ]
    if c.symptoms:
        evidence.append(_ev("Symptoms", ", ".join(SYMPTOM_LABEL[s] for s in c.symptoms)))
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


def _cabin_co2(ctx: EngineContext) -> Insight | None:
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
            _ev(
                f"{_name(ctx, cid)}, 48 h mean",
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
def _safety_insight(ctx: EngineContext, f: SafetyFlag) -> Insight:
    """Nova safety alert: a category (never the astronaut's words), timing, what Nova did, context, a protocol."""
    who = _name(ctx, f.crew_id)
    medical = f.category == "medical"
    crew = ctx.db.crew()
    cdr = next((a for a in crew if a.role == "CDR" and a.id != f.crew_id), None) or next(
        (a for a in crew if a.role == "CMO" and a.id != f.crew_id), None
    )
    cmo = next((a for a in crew if a.role == "CMO" and a.id != f.crew_id), None) or cdr
    helper = cmo if medical else cdr
    delay = ctx.link.delay_seconds / 3600
    signal = SAFETY_SIGNAL_LABEL[f.signal]
    cmo_name = cmo.name if cmo else "the crew medical officer"

    evidence = [
        _ev("Detected", f"{who} {signal}"),
        _ev("When", f"{format_mission_time(f.at)} · reached Earth {format_clock(f.at + delay)}"),
        _ev(
            "Nova already",
            f"told {who} to get {cmo_name} now, stop exercise, and that you were alerted"
            if medical
            else f"gave crisis support, urged {who} not to be alone, and told {who} you were alerted",
        ),
    ]
    mood_b = ctx.db.baseline(f.crew_id, "mood")
    mood = recent_mean(ctx, f.crew_id, "mood", 7)
    if math.isfinite(mood):
        evidence.append(
            _ev(
                "Mood, 7-day mean",
                format_metric("mood", mood),
                reference=format_metric("mood", mood_b.mean) if mood_b else None,
                metric="mood",
                crew_id=f.crew_id,
            )
        )
    sleep = recent_mean(ctx, f.crew_id, "sleepDuration", 5)
    sleep_b = ctx.db.baseline(f.crew_id, "sleepDuration")
    if math.isfinite(sleep):
        evidence.append(
            _ev(
                "Sleep, last 5 nights",
                format_metric("sleepDuration", sleep),
                reference=format_metric("sleepDuration", sleep_b.mean) if sleep_b else None,
                metric="sleepDuration",
                crew_id=f.crew_id,
            )
        )
    hrv = recent_mean(ctx, f.crew_id, "hrv", 7)
    hrv_b = ctx.db.baseline(f.crew_id, "hrv")
    if math.isfinite(hrv):
        evidence.append(
            _ev(
                "HRV, 7-day resting",
                format_metric("hrv", hrv),
                reference=format_metric("hrv", hrv_b.mean) if hrv_b else None,
                metric="hrv",
                crew_id=f.crew_id,
            )
        )
    missed = len(missed_check_in_days(ctx, f.crew_id, 7))
    evidence.append(_ev("Missed check-ins, 7 days", f"{missed}"))
    eva = next_eva_for(ctx, f.crew_id)
    eva_days = math.ceil((eva.start - ctx.hour) / H_PER_DAY) if eva else None
    if eva and eva_days is not None and eva_days <= 7:
        evidence.append(_ev("Upcoming", f"{_short(eva.label)} in {eva_days} d"))
    if helper:
        evidence.append(_ev("On board to help", f"{helper.name} ({helper.role})"))

    if medical:
        recommended = [
            RecommendedAction(
                kind="escalate",
                log="in-person",
                label=f"Ask {cmo.name if cmo else 'the CMO'} to assess {who} now",
                detail="In-person assessment on board; do not wait for Earth.",
            ),
            RecommendedAction(
                kind="message",
                label=f"Message {who}",
                detail="Acknowledge the symptoms and ask for a voice call at the next window.",
            ),
            RecommendedAction(
                kind="escalate",
                log="medical",
                label="Request Earth medical consult",
                detail="Specialist review of symptoms and onboard findings.",
            ),
            RecommendedAction(
                kind="countermeasure",
                countermeasure="rest",
                label="Stop exercise and hazardous tasks",
                detail=f"Pause exercise{f' and {_short(eva.label)} duties' if eva else ''} until cleared.",
            ),
            RecommendedAction(
                kind="escalate",
                label=f"Escalate to {FLIGHT_DIRECTOR}",
                detail="Flight director decides on schedule changes.",
            ),
        ]
    else:
        recommended = [
            RecommendedAction(
                kind="message",
                label=f"Message {who} now",
                detail=f"Let {who} know you got the alert and ask for a call at the next window. Arrives after the signal delay.",
            ),
            RecommendedAction(
                kind="escalate",
                log="in-person",
                label=f"Ask {cdr.name if cdr else 'a crewmate'} to check on {who} in person",
                detail=f"{who} should not be alone right now.",
            ),
            RecommendedAction(
                kind="escalate",
                log="psych",
                label="Book urgent psychologist conference",
                detail="Private conference with the Earth psychologist at the next window.",
            ),
        ]
        if eva and eva_days is not None and eva_days <= 7:
            recommended.append(
                RecommendedAction(
                    kind="countermeasure",
                    countermeasure="rest",
                    label=f"Review {_short(eva.label)} assignment",
                    detail=f"Hold {who}’s role until assessed.",
                )
            )
        recommended.append(
            RecommendedAction(
                kind="escalate",
                label=f"Escalate to {FLIGHT_DIRECTOR}",
                detail="Flight director decides on schedule changes.",
            )
        )

    return Insight(
        id=f"safety:{f.id}",
        crew_id=f.crew_id,
        severity="alert",
        hazards=["distance"] if medical else ["isolation", "distance"],
        title=f"Urgent: {who} {signal}",
        summary=(
            f"In a private Nova conversation at {format_clock(f.at)}, {who} {signal}. "
            f"Nova responded and told {who} that you were alerted. "
            + (f"Get {cmo_name} to {who} now." if medical else f"Contact {who} now and make sure {who} is not alone.")
        ),
        why_it_matters=(
            f"{'These symptoms can signal a life-threatening emergency' if medical else 'This is a risk to life'}, "
            f"and help from Earth is {format_delay(ctx.link.delay_seconds)} away each way. "
            f"The conversation stays private: Nova shares only the type of risk, which {who} agreed to before first use."
        ),
        detected_at=f.at,
        evidence=evidence,
        confidence=0.95,
        recommended=recommended,
    )


def _crew_mode_insights(ctx: EngineContext) -> list[Insight]:
    out: list[Insight] = []
    # Include the current quarter-hour: analysis runs per quarter, alerts carry their exact time.
    out += [_safety_insight(ctx, f) for f in ctx.db.safety_flags() if f.at <= ctx.hour + 0.25]
    for n in (n for n in ctx.db.shared_notes() if n.at <= ctx.hour + 0.25):
        who = _name(ctx, n.crew_id)
        out.append(
            Insight(
                id=f"note:{n.id}",
                crew_id=n.crew_id,
                severity="info",
                hazards=["isolation"],
                title=f"{who} shared a note with you",
                summary=f"“{n.text}”",
                why_it_matters=f"{who} chose to share this from a private Nova conversation. Only this text was shared.",
                detected_at=n.at,
                evidence=[_ev("Source", "Shared from Nova by the astronaut")],
                confidence=1,
                recommended=[
                    RecommendedAction(
                        kind="message", label="Reply", detail=f"Thank {who} and follow up at a convenient time."
                    )
                ],
            )
        )
    for a in (a for a in ctx.db.assignments() if a.status == "done" and (a.completed_at or 0) <= ctx.hour):
        q = QUESTIONNAIRES[a.questionnaire_id]
        who = _name(ctx, a.crew_id)
        score = a.score or 0
        band = "high strain" if score >= 60 else "some strain" if score >= 35 else "low strain"
        comment = next(
            (
                v
                for qq in q.questions
                if qq.kind == "text"
                for v in [a.answers.get(qq.id)]
                if isinstance(v, str) and v.strip()
            ),
            None,
        )
        evidence = [_ev("Score", f"{score}/100", metric=q.feeds, crew_id=a.crew_id)]
        if comment:
            evidence.append(_ev("Comment", f"“{comment}”"))
        out.append(
            Insight(
                id=f"q:{a.id}",
                crew_id=a.crew_id,
                severity="watch" if score >= 60 else "info",
                hazards=q.hazards,
                title=f"{q.title} questionnaire: {band}",
                summary=f"{who} completed the {q.title.lower()} questionnaire. Score {score}/100 (higher means {q.score_meaning}).",
                why_it_matters=q.purpose,
                detected_at=a.completed_at if a.completed_at is not None else ctx.hour,
                primary_metric=q.feeds,
                evidence=evidence,
                confidence=0.8,
                recommended=[
                    RecommendedAction(
                        kind="acknowledge", label="Acknowledge", detail="Review the answers and follow up if needed."
                    )
                ],
            )
        )
    return out


_RULES: list[Rule] = [
    _sleep_debt,
    _isolation_stress,
    _radiation_outlier,
    _fluid_shift,
    _exercise_compliance,
    _bone_on_track,
    _workload_high,
    _check_in_flag,
]


def detect_insights(ctx: EngineContext) -> list[Insight]:
    out: list[Insight] = []
    for a in ctx.db.crew():
        for rule in _RULES:
            i = rule(ctx, a.id)
            if i:
                out.append(i)
    co2 = _cabin_co2(ctx)
    if co2:
        out.append(co2)
    out += _crew_mode_insights(ctx)
    # Nova safety alerts always come first: someone needs help now.
    return sorted(
        out, key=lambda i: (0 if i.id.startswith("safety:") else 1, -SEVERITY_RANK[i.severity], -i.detected_at)
    )

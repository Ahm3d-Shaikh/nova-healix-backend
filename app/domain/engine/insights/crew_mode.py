"""Findings that come from Crew Mode: Nova safety flags (no transcript, by design), shared notes and questionnaires."""

import math

from app.domain.engine.context import (
    H_PER_DAY,
    EngineContext,
    missed_check_in_days,
    next_eva_for,
    recent_mean,
)
from app.domain.engine.insights.common import (
    SAFETY_SIGNAL_LABEL,
    display_name,
    first_word,
    make_evidence,
)
from app.domain.format import format_clock, format_delay, format_metric, format_mission_time
from app.domain.mission_plan import FLIGHT_DIRECTOR
from app.domain.questionnaires import QUESTIONNAIRES
from app.domain.store import SafetyFlag
from app.schemas.assessment import Insight, RecommendedAction


def safety_insight(ctx: EngineContext, f: SafetyFlag) -> Insight:
    """Nova safety alert: a category (never the astronaut's words), timing, what Nova did, context, a protocol."""
    who = display_name(ctx, f.crew_id)
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
        make_evidence("Detected", f"{who} {signal}"),
        make_evidence("When", f"{format_mission_time(f.at)} · reached Earth {format_clock(f.at + delay)}"),
        make_evidence(
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
            make_evidence(
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
            make_evidence(
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
            make_evidence(
                "HRV, 7-day resting",
                format_metric("hrv", hrv),
                reference=format_metric("hrv", hrv_b.mean) if hrv_b else None,
                metric="hrv",
                crew_id=f.crew_id,
            )
        )
    missed = len(missed_check_in_days(ctx, f.crew_id, 7))
    evidence.append(make_evidence("Missed check-ins, 7 days", f"{missed}"))
    eva = next_eva_for(ctx, f.crew_id)
    eva_days = math.ceil((eva.start - ctx.hour) / H_PER_DAY) if eva else None
    if eva and eva_days is not None and eva_days <= 7:
        evidence.append(make_evidence("Upcoming", f"{first_word(eva.label)} in {eva_days} d"))
    if helper:
        evidence.append(make_evidence("On board to help", f"{helper.name} ({helper.role})"))

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
                detail=f"Pause exercise{f' and {first_word(eva.label)} duties' if eva else ''} until cleared.",
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
                    label=f"Review {first_word(eva.label)} assignment",
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


def crew_mode_insights(ctx: EngineContext) -> list[Insight]:
    out: list[Insight] = []
    # Include the current quarter-hour: analysis runs per quarter, alerts carry their exact time.
    out += [safety_insight(ctx, f) for f in ctx.db.safety_flags() if f.at <= ctx.hour + 0.25]
    for n in (n for n in ctx.db.shared_notes() if n.at <= ctx.hour + 0.25):
        who = display_name(ctx, n.crew_id)
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
                evidence=[make_evidence("Source", "Shared from Nova by the astronaut")],
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
        who = display_name(ctx, a.crew_id)
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
        evidence = [make_evidence("Score", f"{score}/100", metric=q.feeds, crew_id=a.crew_id)]
        if comment:
            evidence.append(make_evidence("Comment", f"“{comment}”"))
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

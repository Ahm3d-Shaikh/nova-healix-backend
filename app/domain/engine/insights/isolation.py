"""Isolation stress (several signals moving together) and the ECHO loneliness finding."""

from app.domain import loneliness
from app.domain.engine.context import (
    EngineContext,
    latest,
    missed_check_in_days,
    recent_mean,
)
from app.domain.engine.insights.common import (
    confidence,
    display_name,
    make_evidence,
)
from app.domain.format import format_metric, format_pct
from app.domain.mission_plan import hour_to_day
from app.schemas.assessment import Evidence, Insight, RecommendedAction


def isolation_stress(ctx: EngineContext, crew_id: str) -> Insight | None:
    evidence: list[Evidence] = []
    signals = 0
    mood_b = ctx.db.baseline(crew_id, "mood")
    mood = recent_mean(ctx, crew_id, "mood", 7)
    if mood_b and mood < mood_b.low:
        signals += 1
        evidence.append(
            make_evidence(
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
            make_evidence(
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
            make_evidence(
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
            make_evidence(
                "Missed check-ins, 10 days", f"{len(missed)} ({', '.join(f'D{d}' for d in missed)})", direction="up"
            )
        )
    eff_b = ctx.db.baseline(crew_id, "sleepEfficiency")
    eff = recent_mean(ctx, crew_id, "sleepEfficiency", 7)
    if eff_b and eff < eff_b.low:
        signals += 1
        evidence.append(
            make_evidence(
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
    who = display_name(ctx, crew_id)
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
        confidence=confidence(signals, 0.5),
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


def loneliness_flag(ctx: EngineContext, crew_id: str) -> Insight | None:
    """ECHO check-in: a finding when the latest scored check-in is elevated or raised a safety concern."""
    a = loneliness.current(ctx.db.echo_assessments(crew_id), ctx.hour)
    if a is None or a.status == "nominal":
        return None
    who = display_name(ctx, crew_id)
    return Insight(
        id=f"loneliness:{crew_id}",
        crew_id=crew_id,
        severity="alert" if a.status == "alert" else "watch",
        hazards=["isolation"],
        title="ECHO check-in raised a wellbeing concern" if a.safety_concern else "ECHO check-in: loneliness elevated",
        summary=f"{who}'s ECHO check-in on D{a.mission_day}: {a.what}",
        why_it_matters=a.why,
        detected_at=a.at,
        primary_metric="mood",
        evidence=[
            make_evidence("Loneliness score", f"{a.score}/{loneliness.SCORE_MAX}", crew_id=crew_id),
            make_evidence("Rater confidence", f"{a.confidence:.0%}"),
            make_evidence("Days at 7 or above in a row", f"{a.consecutive_high_days}"),
            make_evidence("Rater note", a.rationale),
        ],
        confidence=a.confidence,
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
                kind="escalate",
                label="Request psych conference",
                detail="Queue a private conference with the Earth-based psychologist.",
            ),
        ],
    )

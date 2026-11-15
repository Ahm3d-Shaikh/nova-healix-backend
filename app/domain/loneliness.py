"""ECHO scoring (pure): the Three-Item Loneliness Scale (Hughes et al. 2004) rated from a check-in chat.

Daily score = sum of three items rated 1-3 (range 3-9).
  nominal  3-5
  watch    6 and above (elevated)
  alert    7 and above on 3 consecutive days, or the check-in raised a safety concern (our rules, illustrative)
A low-confidence rating is stored but never drives the Isolation hazard and is capped at watch
(a safety concern still escalates to alert).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from app.schemas.crew import Status
from app.schemas.echo import LonelinessAssessment, LonelinessRating

ITEMS = (
    "How often do you feel that you lack companionship?",
    "How often do you feel left out?",
    "How often do you feel isolated from others?",
)
SCORE_MIN = 3  # [PAPER]
SCORE_MAX = 9  # [PAPER]
WATCH_MIN = 6  # [PAPER] 6-9 elevated
ALERT_MIN = 7  # [OURS]
ALERT_DAYS = 3  # [OURS]
MIN_TURNS = 3  # [OURS] astronaut replies needed before the chat can be scored
MAX_TURNS = 10  # [OURS] astronaut replies after which the chat must be scored
MIN_CONFIDENCE = 0.6  # [OURS] below this a rating is stored but never drives the hazard
LOOKAHEAD_H = 0.25  # analysis is cached per quarter hour, so include a check-in made in the current one

SOURCE = (
    "Three-Item Loneliness Scale (Hughes et al., 2004) rated from an AI check-in; alert rules are ours (illustrative)"
)
WHY = "Prolonged isolation and confinement raise the risk of mood and performance decline."

DayScore = tuple[int, int]  # (mission day, score)


@dataclass(frozen=True)
class Verdict:
    status: Status
    what: str
    action: str


def high_streak(series: Sequence[DayScore]) -> int:
    """Consecutive calendar days, ending with the latest, whose score is at or above the alert threshold."""
    streak = 0
    expected = series[-1][0] if series else 0
    for day, score in reversed(series):
        if day != expected or score < ALERT_MIN:
            break
        streak += 1
        expected -= 1
    return streak


def assess(series: Sequence[DayScore], *, safety_concern: bool = False) -> Verdict:
    """Verdict for a series of (day, score) pairs, latest last."""
    if not series:
        return Verdict("nominal", "No check-in yet.", "No action needed.")
    latest = series[-1][1]
    if safety_concern:
        return Verdict(
            "alert",
            f"Today's check-in raised a wellbeing concern (loneliness score {latest}/{SCORE_MAX}).",
            "Arrange a private conference with the flight surgeon or psychologist today.",
        )
    streak = high_streak(series)
    if streak >= ALERT_DAYS:
        return Verdict(
            "alert",
            f"Loneliness score {latest}/{SCORE_MAX}; at {ALERT_MIN} or above for {streak} consecutive days.",
            "Schedule a private call with a flight surgeon or psychologist and increase crew contact.",
        )
    if latest >= WATCH_MIN:
        return Verdict(
            "watch",
            f"Loneliness score {latest}/{SCORE_MAX} ({WATCH_MIN} or above = elevated).",
            "Plan social time with crew and a call home; check in again tomorrow.",
        )
    return Verdict("nominal", f"Loneliness score {latest}/{SCORE_MAX} (3-5 = low).", "No action needed.")


def score_rating(
    rating: LonelinessRating,
    prior: Sequence[DayScore],
    *,
    session_id: str,
    crew_id: str,
    day: int,
    at: float,
    model: str,
) -> LonelinessAssessment:
    """Turn a rater response into an assessment. `prior` holds the earlier days' reliable scores."""
    q1, q2, q3 = rating.lack_companionship.rating, rating.left_out.rating, rating.isolated.rating
    score = q1 + q2 + q3
    confidence = min(1.0, max(0.0, rating.confidence))
    reliable = confidence >= MIN_CONFIDENCE
    series = [*(p for p in prior if p[0] < day), (day, score)]
    verdict = assess(series, safety_concern=rating.safety_concern)
    status = verdict.status
    what, action = verdict.what, verdict.action
    if not reliable:
        if status == "alert" and not rating.safety_concern:
            status = "watch"
        what = f"{what} Low-confidence rating ({confidence:.0%})."
        action = f"{action} Repeat the check-in with more detail to confirm."
    return LonelinessAssessment(
        id=str(uuid.uuid4()),
        session_id=session_id,
        crew_id=crew_id,
        mission_day=day,
        at=at,
        q1=q1,
        q2=q2,
        q3=q3,
        score=score,
        confidence=round(confidence, 3),
        reliable=reliable,
        safety_concern=rating.safety_concern,
        status=status,
        consecutive_high_days=high_streak(series),
        rationale=rating.rationale,
        evidence=[rating.lack_companionship.evidence, rating.left_out.evidence, rating.isolated.evidence],
        what=what,
        why=WHY,
        action=action,
        source=SOURCE,
        model=model,
        created_at=datetime.now(UTC),
    )


def day_scores(assessments: Sequence[LonelinessAssessment]) -> list[DayScore]:
    """One (day, score) per mission day from reliable assessments, the latest of each day, oldest first."""
    by_day: dict[int, int] = {}
    for a in assessments:  # oldest first, so a later check-in on the same day wins
        if a.reliable:
            by_day[a.mission_day] = a.score
    return sorted(by_day.items())


def current(assessments: Sequence[LonelinessAssessment], hour: float) -> LonelinessAssessment | None:
    """The latest assessment that should drive the hazard at `hour`: reliable, or one raising a safety concern."""
    visible = [a for a in assessments if a.at <= hour + LOOKAHEAD_H and (a.reliable or a.safety_concern)]
    return visible[-1] if visible else None

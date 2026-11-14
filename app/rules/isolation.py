"""I - Isolation: Three-Item Loneliness Scale (Hughes et al. 2004), scored from AI check-in chats.

Daily score = sum of three items rated 1-3 (range 3-9).
  green  3-5
  amber  >= 6 (elevated)
  red    >= 7 on 3 consecutive days, or the check-in raised a safety concern (our rules, illustrative)
"""

from collections.abc import Sequence

from app.models.alert import Alert
from app.models.enums import Hazard, Level
from app.rules import thresholds as t
from app.rules.context import RuleContext
from app.rules.stats import trailing_streak

ITEMS = (
    "How often do you feel that you lack companionship?",
    "How often do you feel left out?",
    "How often do you feel isolated from others?",
)
SRC = "Three-Item Loneliness Scale (Hughes et al., 2004) rated from an AI check-in; red rules are ours (illustrative)"
WHY = "Prolonged isolation and confinement raise the risk of mood and performance decline."


def evaluate(ctx: RuleContext) -> list[Alert]:
    safety = bool(ctx.records) and ctx.records[-1].isolation_safety_flag
    return [assess([r.loneliness_total for r in ctx.records], safety_concern=safety)]


def high_streak(totals: Sequence[int]) -> int:
    """Consecutive most-recent days with a score at or above the red threshold."""
    return trailing_streak([score >= t.LONELINESS_RED_MIN for score in totals])


def assess(totals: Sequence[int], *, safety_concern: bool = False) -> Alert:
    """Alert for a series of daily loneliness totals (latest last)."""
    if not totals:
        return _alert(Level.GREEN, "No check-in yet.", "No action needed.")
    latest = totals[-1]
    if safety_concern:
        return _alert(
            Level.RED,
            f"Today's check-in raised a wellbeing concern (loneliness score {latest}/{t.LONELINESS_MAX}).",
            "Arrange a private conference with the flight surgeon or psychologist today.",
        )
    streak = high_streak(totals)
    if streak >= t.LONELINESS_RED_DAYS:
        return _alert(
            Level.RED,
            f"Loneliness score {latest}/{t.LONELINESS_MAX}; ≥{t.LONELINESS_RED_MIN} for {streak} consecutive days.",
            "Schedule a private call with a flight surgeon or psychologist and increase crew contact.",
        )
    if latest >= t.LONELINESS_AMBER_MIN:
        return _alert(
            Level.AMBER,
            f"Loneliness score {latest}/{t.LONELINESS_MAX} (≥{t.LONELINESS_AMBER_MIN} = elevated).",
            "Plan social time with crew and a call home; check in again tomorrow.",
        )
    return _alert(Level.GREEN, f"Loneliness score {latest}/{t.LONELINESS_MAX} (3–5 = low).", "No action needed.")


def _alert(level: Level, what: str, action: str) -> Alert:
    return Alert(
        rule="I.loneliness",
        hazard=Hazard.ISOLATION,
        level=level,
        what=what,
        why=WHY,
        action=action,
        source=SRC,
    )

"""I - Isolation (Three-Item Loneliness Scale, Hughes et al. 2004)."""

from collections.abc import Sequence

from app.models.alert import Alert
from app.models.enums import Hazard, Level
from app.rules import thresholds as t
from app.rules.context import RuleContext
from app.rules.stats import trailing_streak

QUESTIONS = (
    "How often do you feel that you lack companionship?",
    "How often do you feel left out?",
    "How often do you feel isolated from others?",
)
SRC = "Three-Item Loneliness Scale (Hughes et al., 2004); red rule is ours (illustrative)"
WHY = "Prolonged isolation and confinement raise the risk of mood and performance decline."


def evaluate(ctx: RuleContext) -> list[Alert]:
    return [assess([r.loneliness_total for r in ctx.records])]


def high_streak(totals: Sequence[int]) -> int:
    """Consecutive most-recent days with a score at or above the red threshold."""
    return trailing_streak([score >= t.LONELINESS_RED_MIN for score in totals])


def assess(totals: Sequence[int]) -> Alert:
    """Alert for a series of daily loneliness totals (latest last)."""
    if not totals:
        return _alert(Level.GREEN, "No questionnaire answers yet.", "No action needed.")
    latest = totals[-1]
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
            f"Loneliness score {latest}/{t.LONELINESS_MAX} (6–9 = elevated).",
            "Plan social time with crew and a call home; re-check tomorrow.",
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

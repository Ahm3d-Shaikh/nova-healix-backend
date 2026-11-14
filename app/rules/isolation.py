"""I — Isolation (Three-Item Loneliness Scale, Hughes et al. 2004)."""

from app.models.alert import Alert
from app.models.enums import Hazard, Level
from app.rules.context import RuleContext
from app.rules.stats import trailing_streak

QUESTIONS = (
    "How often do you feel that you lack companionship?",
    "How often do you feel left out?",
    "How often do you feel isolated from others?",
)
SRC = "Three-Item Loneliness Scale (Hughes et al., 2004); red rule is ours (illustrative)"


def evaluate(ctx: RuleContext) -> list[Alert]:
    totals = [r.loneliness_total for r in ctx.records]
    if not totals:
        return [_alert(Level.GREEN, "No questionnaire answers yet.", "No action needed.")]
    latest = totals[-1]
    streak = trailing_streak([t >= 7 for t in totals])

    if streak >= 3:
        return [_alert(
            Level.RED, f"Loneliness score {latest}/9; ≥7 for {streak} consecutive days.",
            "Schedule a private call with a flight surgeon or psychologist and increase crew contact.",
        )]
    if latest >= 6:
        return [_alert(
            Level.AMBER, f"Loneliness score {latest}/9 (6–9 = elevated).",
            "Plan social time with crew and a call home; re-check tomorrow.",
        )]
    return [_alert(Level.GREEN, f"Loneliness score {latest}/9 (3–5 = low).", "No action needed.")]


def _alert(level: Level, what: str, action: str) -> Alert:
    return Alert(
        rule="I.loneliness", hazard=Hazard.ISOLATION, level=level, what=what,
        why="Prolonged isolation and confinement raise the risk of mood and performance decline.",
        action=action, source=SRC,
    )

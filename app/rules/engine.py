"""Runs every rule for one astronaut-day. Card level = worst of its rules."""

from collections.abc import Callable

from app.models.alert import Alert
from app.models.crew import CardStatus
from app.models.enums import HAZARD_LABELS, Hazard, Level, worst
from app.rules import distance, environment, gravity, isolation, mirror_gap, radiation
from app.rules.context import RuleContext
from app.rules.metrics import card_metrics

RuleModule = Callable[[RuleContext], list[Alert]]

RULES: dict[Hazard, RuleModule] = {
    Hazard.RADIATION: radiation.evaluate,
    Hazard.ISOLATION: isolation.evaluate,
    Hazard.DISTANCE: distance.evaluate,
    Hazard.GRAVITY: gravity.evaluate,
    Hazard.ENVIRONMENT: environment.evaluate,
    Hazard.MIRROR: mirror_gap.evaluate,
}


def evaluate_cards(ctx: RuleContext) -> list[CardStatus]:
    cards = []
    for hazard, rule in RULES.items():
        alerts = rule(ctx)
        cards.append(
            CardStatus(
                hazard=hazard,
                label=HAZARD_LABELS[hazard],
                level=worst([a.level for a in alerts]),
                alerts=alerts,
                metrics=card_metrics(hazard, ctx),
            )
        )
    return cards


def overall_level(cards: list[CardStatus]) -> Level:
    return worst([c.level for c in cards])


def flagged_alerts(cards: list[CardStatus]) -> list[Alert]:
    """Amber/red results only (what the crew alert panel shows), worst first."""
    flagged = [a for c in cards for a in c.alerts if a.level != Level.GREEN]
    return sorted(flagged, key=lambda a: -a.level.rank)

"""D — Distance from Earth: comms delay and data freshness."""

from app.models.alert import Alert
from app.models.enums import COMMS_DELAY, DataSource, Hazard, Level
from app.rules.context import RuleContext

SRC = (
    "Mission comms delay figures as used by AURORA; DONKI feed status from this app; amber rule is ours (illustrative)"
)


def evaluate(ctx: RuleContext) -> list[Alert]:
    delay = COMMS_DELAY[ctx.mission]
    stale = ctx.deep_space_mode or ctx.weather_source != DataSource.LIVE
    if stale:
        return [
            Alert(
                rule="D.data_freshness",
                hazard=Hazard.DISTANCE,
                level=Level.AMBER,
                what=f"Running on cached data from {ctx.weather_as_of:%Y-%m-%d} "
                f"({'deep space mode' if ctx.deep_space_mode else 'live DONKI unavailable'}). "
                f"One-way comms delay: {delay}.",
                why="Far from Earth, live links are slow or lost and the crew must act on stored data.",
                action="Rely on onboard data; re-sync with Mission Control when the link returns.",
                source=SRC,
            )
        ]
    return [
        Alert(
            rule="D.data_freshness",
            hazard=Hazard.DISTANCE,
            level=Level.GREEN,
            what=f"Live NASA DONKI link OK. One-way comms delay: {delay}.",
            why="Distance from Earth limits real-time support and resupply.",
            action="No action needed.",
            source=SRC,
        )
    ]

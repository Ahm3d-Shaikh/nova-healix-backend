"""D — Distance from Earth: real signal delay (JPL Horizons) and data freshness."""

from app.models.alert import Alert
from app.models.enums import COMMS_DELAY, DataSource, Hazard, Level
from app.rules import thresholds as t
from app.rules.context import RuleContext

SRC_FRESH = "NASA DONKI / JPL Horizons feed status from this app"
SRC_DELAY = "NASA JPL Horizons ephemeris (one-way light time); alert cut-off is ours (illustrative)"
AU_KM = 149_597_870.7


def evaluate(ctx: RuleContext) -> list[Alert]:
    return [_comms_delay(ctx), _data_freshness(ctx)]


def format_delay(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60:
        return f"{seconds:.1f} s"
    minutes, secs = divmod(round(seconds), 60)
    return f"{minutes} min {secs:02d} s"


def comms_delay_text(ctx: RuleContext) -> str:
    return format_delay(ctx.distance.light_time_s) if ctx.distance else COMMS_DELAY[ctx.mission]


def _comms_delay(ctx: RuleContext) -> Alert:
    d = ctx.distance
    if d is None:
        return Alert(
            rule="D.comms_delay",
            hazard=Hazard.DISTANCE,
            level=Level.GREEN,
            what=f"No ephemeris available; typical one-way delay for this mission: {COMMS_DELAY[ctx.mission]}.",
            why="Distance from Earth limits real-time support and resupply.",
            action="No action needed.",
            source="Typical mission figures",
        )
    where = f"{ctx.distance_target or ctx.mission.value}: {d.distance_km:,.0f} km from Earth"
    if d.distance_km > AU_KM / 100:
        where += f" ({d.distance_km / AU_KM:.2f} AU)"
    delay = f"one-way signal delay {format_delay(d.light_time_s)} (round trip {format_delay(2 * d.light_time_s)})"
    if d.light_time_s >= t.DISTANCE_AMBER_LIGHT_TIME_S:
        return Alert(
            rule="D.comms_delay",
            hazard=Hazard.DISTANCE,
            level=Level.AMBER,
            what=f"{where}; {delay}.",
            why="With a delay this long, Mission Control cannot guide a medical event in real time.",
            action="Treat medical issues with onboard protocols first; send Mission Control a written summary.",
            source=SRC_DELAY,
        )
    realtime = d.light_time_s < t.REALTIME_COMMS_MAX_S
    return Alert(
        rule="D.comms_delay",
        hazard=Hazard.DISTANCE,
        level=Level.GREEN,
        what=f"{where}; {delay}.",
        why="Distance from Earth limits real-time support and resupply.",
        action="No action needed." if realtime else "Expect short pauses on voice loops.",
        source=SRC_DELAY,
    )


def _data_freshness(ctx: RuleContext) -> Alert:
    stale_feeds = []
    if ctx.deep_space_mode or ctx.weather_source != DataSource.LIVE:
        stale_feeds.append(f"space weather from {ctx.weather_as_of:%Y-%m-%d}")
    distance_stale = ctx.deep_space_mode or ctx.distance_source not in {None, DataSource.LIVE}
    if distance_stale and ctx.distance_as_of is not None:
        stale_feeds.append(f"ephemeris from {ctx.distance_as_of:%Y-%m-%d}")
    if stale_feeds:
        why_stale = "deep space mode" if ctx.deep_space_mode else "live NASA feeds unavailable"
        return Alert(
            rule="D.data_freshness",
            hazard=Hazard.DISTANCE,
            level=Level.AMBER,
            what=f"Running on cached data ({'; '.join(stale_feeds)}; {why_stale}). "
            f"One-way comms delay: {comms_delay_text(ctx)}.",
            why="Far from Earth, live links are slow or lost and the crew must act on stored data.",
            action="Rely on onboard data; re-sync with Mission Control when the link returns.",
            source=SRC_FRESH,
        )
    return Alert(
        rule="D.data_freshness",
        hazard=Hazard.DISTANCE,
        level=Level.GREEN,
        what=f"Live NASA links OK. One-way comms delay: {comms_delay_text(ctx)}.",
        why="Distance from Earth limits real-time support and resupply.",
        action="No action needed.",
        source=SRC_FRESH,
    )

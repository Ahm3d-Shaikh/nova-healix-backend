"""R - Radiation."""

from datetime import timedelta

from app.models.alert import Alert
from app.models.enums import EventKind, Hazard, Level
from app.models.space_weather import SpaceWeatherEvent
from app.rules import thresholds as t
from app.rules.context import RuleContext

SRC_DONKI = "NASA DONKI; event-to-level mapping is ours (illustrative)"
SRC_LIMITS = "NASA-STD-3001 (limits); alert cut-offs are ours (illustrative)"


def evaluate(ctx: RuleContext) -> list[Alert]:
    return [_sep(ctx), _flare_or_cme(ctx), _cumulative_dose(ctx), _event_dose(ctx)]


def recent_events(ctx: RuleContext, kind: EventKind) -> list[SpaceWeatherEvent]:
    since = ctx.now - timedelta(hours=t.EVENT_LOOKBACK_HOURS)
    return [e for e in ctx.events if e.kind == kind and since < e.time <= ctx.now]


def is_alert_flare(event: SpaceWeatherEvent) -> bool:
    return (event.class_type or "").upper().startswith(t.FLARE_ALERT_CLASS)


def _sep(ctx: RuleContext) -> Alert:
    seps = recent_events(ctx, EventKind.SEP)
    if not seps:
        return Alert(
            rule="R.sep_24h",
            hazard=Hazard.RADIATION,
            level=Level.GREEN,
            what="No solar energetic particle (SEP) event in the last 24 h.",
            why="SEP events can sharply raise radiation dose.",
            action="No action needed.",
            source=SRC_DONKI,
        )
    latest = max(seps, key=lambda e: e.time)
    return Alert(
        rule="R.sep_24h",
        hazard=Hazard.RADIATION,
        level=Level.RED,
        what=f"{len(seps)} SEP detection(s) in the last 24 h (latest {latest.time:%Y-%m-%d %H:%M} UTC).",
        why="Energetic solar particles penetrate hull and tissue and can deliver a large dose in hours.",
        action="Move to shielded area.",
        source=SRC_DONKI,
    )


def _flare_or_cme(ctx: RuleContext) -> Alert:
    flares = [e for e in recent_events(ctx, EventKind.FLARE) if is_alert_flare(e)]
    cmes = recent_events(ctx, EventKind.CME)
    if not flares and not cmes:
        return Alert(
            rule="R.flare_cme_24h",
            hazard=Hazard.RADIATION,
            level=Level.GREEN,
            what="No X-class flare or CME in the last 24 h.",
            why="Strong flares and CMEs often precede particle storms.",
            action="No action needed.",
            source=SRC_DONKI,
        )
    parts = []
    if flares:
        parts.append("X-class flare(s): " + ", ".join(sorted({f.class_type for f in flares if f.class_type})))
    if cmes:
        parts.append(f"{len(cmes)} CME(s)")
    return Alert(
        rule="R.flare_cme_24h",
        hazard=Hazard.RADIATION,
        level=Level.AMBER,
        what="; ".join(parts) + " in the last 24 h.",
        why="Strong flares and CMEs often precede particle storms.",
        action="Watch: monitor DONKI alerts and be ready to shelter.",
        source=SRC_DONKI,
    )


def _cumulative_dose(ctx: RuleContext) -> Alert:
    total = sum(r.dose_msv for r in ctx.records)
    frac = total / t.CAREER_DOSE_LIMIT_MSV
    if frac >= t.CAREER_RED_FRACTION:
        level = Level.RED
    elif frac >= t.CAREER_AMBER_FRACTION:
        level = Level.AMBER
    else:
        level = Level.GREEN
    return Alert(
        rule="R.cumulative_dose",
        hazard=Hazard.RADIATION,
        level=level,
        what=(
            f"Cumulative dose {total:.1f} mSv = {frac:.1%} of the {t.CAREER_DOSE_LIMIT_MSV:.0f} mSv "
            f"career limit. Estimated neutron share ≈{t.NEUTRON_SHARE:.0%} "
            f"(~{total * t.NEUTRON_SHARE:.1f} mSv; ISS neutron dose ≈{t.ISS_NEUTRON_USV_PER_DAY} µSv/day) "
            "- estimate."
        ),
        why="Career dose limits cap lifetime cancer risk.",
        action="No action needed." if level == Level.GREEN else "Review dose budget with flight surgeon.",
        source=SRC_LIMITS + "; neutron figures: CSA Radi-N2; daily dose is simulated",
    )


def _event_dose(ctx: RuleContext) -> Alert:
    peak = max((r.dose_msv for r in ctx.records), default=0.0)
    over = peak > t.SPE_DOSE_LIMIT_MSV
    return Alert(
        rule="R.event_dose",
        hazard=Hazard.RADIATION,
        level=Level.RED if over else Level.GREEN,
        what=f"Highest single-day dose {peak:.1f} mSv vs {t.SPE_DOSE_LIMIT_MSV:.0f} mSv per-event limit.",
        why="NASA limits the dose from any single solar particle event.",
        action="Shelter and notify flight surgeon." if over else "No action needed.",
        source=SRC_LIMITS + "; daily dose is simulated",
    )

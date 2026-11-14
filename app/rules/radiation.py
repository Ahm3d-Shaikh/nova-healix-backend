"""R — Radiation."""

from datetime import timedelta

from app.models.alert import Alert
from app.models.enums import EventKind, Hazard, Level
from app.rules.context import RuleContext

CAREER_LIMIT_MSV = 600.0  # NASA-STD-3001
SPE_LIMIT_MSV = 250.0  # NASA-STD-3001, per solar particle event
AMBER_FRACTION = 0.80  # cut-offs are ours (illustrative)
RED_FRACTION = 0.95
NEUTRON_SHARE = 0.30  # CSA Radi-N2 (estimate)
ISS_NEUTRON_USV_PER_DAY = 150  # CSA Radi-N2

SRC_DONKI = "NASA DONKI; event-to-level mapping is ours (illustrative)"
SRC_LIMITS = "NASA-STD-3001 (limits); alert cut-offs are ours (illustrative)"


def evaluate(ctx: RuleContext) -> list[Alert]:
    return [_sep(ctx), _flare_or_cme(ctx), _cumulative_dose(ctx), _event_dose(ctx)]


def _recent(ctx: RuleContext, kind: EventKind):
    since = ctx.now - timedelta(hours=24)
    return [e for e in ctx.events if e.kind == kind and since < e.time <= ctx.now]


def _sep(ctx: RuleContext) -> Alert:
    seps = _recent(ctx, EventKind.SEP)
    if not seps:
        return Alert(
            rule="R.sep_24h", hazard=Hazard.RADIATION, level=Level.GREEN,
            what="No solar energetic particle (SEP) event in the last 24 h.",
            why="SEP events can sharply raise radiation dose.",
            action="No action needed.", source=SRC_DONKI,
        )
    latest = max(seps, key=lambda e: e.time)
    return Alert(
        rule="R.sep_24h", hazard=Hazard.RADIATION, level=Level.RED,
        what=f"{len(seps)} SEP detection(s) in the last 24 h (latest {latest.time:%Y-%m-%d %H:%M} UTC).",
        why="Energetic solar particles penetrate hull and tissue and can deliver a large dose in hours.",
        action="Move to shielded area.", source=SRC_DONKI,
    )


def _flare_or_cme(ctx: RuleContext) -> Alert:
    flares = [e for e in _recent(ctx, EventKind.FLARE) if (e.class_type or "").upper().startswith("X")]
    cmes = _recent(ctx, EventKind.CME)
    if not flares and not cmes:
        return Alert(
            rule="R.flare_cme_24h", hazard=Hazard.RADIATION, level=Level.GREEN,
            what="No X-class flare or CME in the last 24 h.",
            why="Strong flares and CMEs often precede particle storms.",
            action="No action needed.", source=SRC_DONKI,
        )
    parts = []
    if flares:
        parts.append("X-class flare(s): " + ", ".join(sorted({f.class_type for f in flares if f.class_type})))
    if cmes:
        parts.append(f"{len(cmes)} CME(s)")
    return Alert(
        rule="R.flare_cme_24h", hazard=Hazard.RADIATION, level=Level.AMBER,
        what="; ".join(parts) + " in the last 24 h.",
        why="Strong flares and CMEs often precede particle storms.",
        action="Watch: monitor DONKI alerts and be ready to shelter.", source=SRC_DONKI,
    )


def _cumulative_dose(ctx: RuleContext) -> Alert:
    total = sum(r.dose_msv for r in ctx.records)
    frac = total / CAREER_LIMIT_MSV
    level = Level.RED if frac >= RED_FRACTION else Level.AMBER if frac >= AMBER_FRACTION else Level.GREEN
    neutron = total * NEUTRON_SHARE
    return Alert(
        rule="R.cumulative_dose", hazard=Hazard.RADIATION, level=level,
        what=(
            f"Cumulative dose {total:.1f} mSv = {frac:.1%} of the {CAREER_LIMIT_MSV:.0f} mSv career limit. "
            f"Estimated neutron share ≈{NEUTRON_SHARE:.0%} (~{neutron:.1f} mSv; ISS neutron dose "
            f"≈{ISS_NEUTRON_USV_PER_DAY} µSv/day) — estimate."
        ),
        why="Career dose limits cap lifetime cancer risk.",
        action="No action needed." if level == Level.GREEN else "Review dose budget with flight surgeon.",
        source=SRC_LIMITS + "; neutron figures: CSA Radi-N2; daily dose is simulated",
    )


def _event_dose(ctx: RuleContext) -> Alert:
    peak = max((r.dose_msv for r in ctx.records), default=0.0)
    over = peak > SPE_LIMIT_MSV
    return Alert(
        rule="R.event_dose", hazard=Hazard.RADIATION,
        level=Level.RED if over else Level.GREEN,
        what=f"Highest single-day dose {peak:.1f} mSv vs {SPE_LIMIT_MSV:.0f} mSv per-event limit.",
        why="NASA limits the dose from any single solar particle event.",
        action="Shelter and notify flight surgeon." if over else "No action needed.",
        source=SRC_LIMITS + "; daily dose is simulated",
    )

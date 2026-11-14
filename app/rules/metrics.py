"""Structured numbers behind each card, so the dashboard never parses alert text."""

from datetime import timedelta

from app.models.crew import MetricValue
from app.models.enums import COMMS_DELAY, EventKind, Hazard
from app.rules import gravity, mirror_gap, radiation
from app.rules.context import RuleContext
from app.rules.stats import mean_sd, trailing_streak

Metrics = dict[str, MetricValue]


def card_metrics(hazard: Hazard, ctx: RuleContext) -> Metrics:
    return _BUILDERS[hazard](ctx)


def _radiation(ctx: RuleContext) -> Metrics:
    total = sum(r.dose_msv for r in ctx.records)
    since = ctx.now - timedelta(hours=24)
    recent = [e for e in ctx.events if since < e.time <= ctx.now]
    return {
        "cumulative_dose_msv": round(total, 2),
        "career_limit_msv": radiation.CAREER_LIMIT_MSV,
        "percent_of_limit": round(100 * total / radiation.CAREER_LIMIT_MSV, 2),
        "latest_daily_dose_msv": ctx.records[-1].dose_msv,
        "neutron_share_estimate": radiation.NEUTRON_SHARE,
        "neutron_dose_estimate_msv": round(total * radiation.NEUTRON_SHARE, 2),
        "iss_neutron_usv_per_day": radiation.ISS_NEUTRON_USV_PER_DAY,
        "sep_events_24h": sum(e.kind == EventKind.SEP for e in recent),
        "x_flares_24h": sum(e.kind == EventKind.FLARE and (e.class_type or "").startswith("X") for e in recent),
        "cmes_24h": sum(e.kind == EventKind.CME for e in recent),
        "data_source": ctx.weather_source.value,
        "data_as_of": ctx.weather_as_of.isoformat(),
    }


def _isolation(ctx: RuleContext) -> Metrics:
    totals = [r.loneliness_total for r in ctx.records]
    return {
        "loneliness_score": totals[-1], "scale_min": 3, "scale_max": 9,
        "consecutive_days_at_or_above_7": trailing_streak([t >= 7 for t in totals]),
        "history": totals,
    }


def _distance(ctx: RuleContext) -> Metrics:
    return {
        "mission": ctx.mission.value, "comms_delay": COMMS_DELAY[ctx.mission],
        "deep_space_mode": ctx.deep_space_mode, "data_source": ctx.weather_source.value,
        "data_as_of": ctx.weather_as_of.isoformat(),
    }


def _gravity(ctx: RuleContext) -> Metrics:
    r = ctx.records[-1]
    out: Metrics = {
        "baseline_ready": len(ctx.records) > gravity.BASELINE_DAYS,
        "exercise_min": r.exercise_min,
        "exercise_missed_days": trailing_streak(
            [x.exercise_min < gravity.MISSED_EXERCISE_MIN for x in ctx.records]),
    }
    base = ctx.records[: gravity.BASELINE_DAYS]
    for attr, (_label, _unit, floor) in gravity.METRICS.items():
        out[attr] = getattr(r, attr)
        if out["baseline_ready"]:
            mu, sd = mean_sd([getattr(x, attr) for x in base], floor)
            out[f"{attr}_baseline_mean"] = round(mu, 2)
            out[f"{attr}_threshold"] = round(mu + gravity.SD_MULTIPLIER * sd, 2)
    out["drifting"] = ", ".join(gravity._drifting_metrics(list(ctx.records))) if out["baseline_ready"] else ""
    return out


def _environment(ctx: RuleContext) -> Metrics:
    r = ctx.records[-1]
    return {
        "co2_mmhg_1h": r.co2_mmhg_1h, "co2_1h_limit": 3.0,
        "co2_mmhg_7d": r.co2_mmhg_7d, "co2_7d_limit": 2.5,
        "cabin_temp_c": r.cabin_temp_c, "temp_min_c": 18.0, "temp_max_c": 27.0,
    }


def _mirror(ctx: RuleContext) -> Metrics:
    gaps = mirror_gap.gap_series(ctx.records)
    r = ctx.records[-1]
    return {
        "gap": None if gaps[-1] is None else round(gaps[-1], 3),
        "amber_gap": mirror_gap.AMBER_GAP, "red_gap": mirror_gap.RED_GAP,
        "self_rating": r.self_rating, "pvt_mean_rt_ms": r.pvt_mean_rt,
        "pvt_lapses": r.pvt_lapses, "lapse_band": mirror_gap.lapse_band_label(r.pvt_lapses),
        "baseline_sessions": mirror_gap.BASELINE_SESSIONS,
    }


_BUILDERS = {
    Hazard.RADIATION: _radiation, Hazard.ISOLATION: _isolation, Hazard.DISTANCE: _distance,
    Hazard.GRAVITY: _gravity, Hazard.ENVIRONMENT: _environment, Hazard.MIRROR: _mirror,
}

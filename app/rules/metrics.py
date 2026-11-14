"""Typed numbers behind each card, so the dashboard never parses alert text."""

from collections.abc import Callable

from app.models.enums import EventKind, Hazard
from app.models.metrics import (
    CardMetrics,
    DistanceMetrics,
    EnvironmentMetrics,
    GravityMetrics,
    IsolationMetrics,
    MirrorMetrics,
    RadiationMetrics,
    Vital,
)
from app.rules import distance, gravity, isolation, mirror_gap, radiation
from app.rules import thresholds as t
from app.rules.context import RuleContext


def card_metrics(hazard: Hazard, ctx: RuleContext) -> CardMetrics:
    return _BUILDERS[hazard](ctx)


def _radiation(ctx: RuleContext) -> RadiationMetrics:
    total = sum(r.dose_msv for r in ctx.records)
    return RadiationMetrics(
        cumulative_dose_msv=round(total, 2),
        career_limit_msv=t.CAREER_DOSE_LIMIT_MSV,
        percent_of_limit=round(100 * total / t.CAREER_DOSE_LIMIT_MSV, 2),
        latest_daily_dose_msv=ctx.records[-1].dose_msv,
        neutron_share_estimate=t.NEUTRON_SHARE,
        neutron_dose_estimate_msv=round(total * t.NEUTRON_SHARE, 2),
        iss_neutron_usv_per_day=t.ISS_NEUTRON_USV_PER_DAY,
        sep_events_24h=len(radiation.recent_events(ctx, EventKind.SEP)),
        x_flares_24h=sum(radiation.is_alert_flare(e) for e in radiation.recent_events(ctx, EventKind.FLARE)),
        cmes_24h=len(radiation.recent_events(ctx, EventKind.CME)),
        data_source=ctx.weather_source.value,
        data_as_of=ctx.weather_as_of.isoformat(),
    )


def _isolation(ctx: RuleContext) -> IsolationMetrics:
    totals = [r.loneliness_total for r in ctx.records]
    direction, delta = isolation.trend(totals)
    latest = ctx.records[-1]
    return IsolationMetrics(
        loneliness_score=totals[-1],
        scale_min=t.LONELINESS_MIN,
        scale_max=t.LONELINESS_MAX,
        amber_threshold=t.LONELINESS_AMBER_MIN,
        red_threshold=t.LONELINESS_RED_MIN,
        red_consecutive_days=t.LONELINESS_RED_DAYS,
        consecutive_days_at_or_above_7=isolation.high_streak(totals),
        trend=direction,
        trend_delta=delta,
        latest_source=latest.loneliness_source,
        safety_concern=latest.isolation_safety_flag,
        ai_checkin_days=[r.day for r in ctx.records if r.loneliness_source == "ai_checkin"],
        history=totals,
    )


def _distance(ctx: RuleContext) -> DistanceMetrics:
    d = ctx.distance
    return DistanceMetrics(
        mission=ctx.mission.value,
        comms_delay=distance.comms_delay_text(ctx),
        deep_space_mode=ctx.deep_space_mode,
        data_source=ctx.weather_source.value,
        data_as_of=ctx.weather_as_of.isoformat(),
        target_name=ctx.distance_target,
        distance_km=None if d is None else round(d.distance_km, 1),
        distance_au=None if d is None else round(d.distance_km / distance.AU_KM, 6),
        one_way_light_time_s=None if d is None else round(d.light_time_s, 3),
        round_trip_light_time_s=None if d is None else round(2 * d.light_time_s, 3),
        range_rate_km_s=None if d is None else round(d.range_rate_km_s, 4),
        distance_source=None if ctx.distance_source is None else ctx.distance_source.value,
        distance_as_of=None if ctx.distance_as_of is None else ctx.distance_as_of.isoformat(),
    )


def _gravity(ctx: RuleContext) -> GravityMetrics:
    ready = gravity.baseline_ready(ctx.records)
    latest = ctx.records[-1]
    drifting = gravity.drifting_metrics(ctx.records)
    vitals: dict[str, Vital] = {}
    for spec in gravity.VITALS:
        value = getattr(latest, spec.attr)
        if ready:
            base = gravity.vital_baseline(ctx.records, spec)
            vitals[spec.attr] = Vital(
                value=value,
                baseline_mean=round(base.mean, 2),
                threshold=round(base.threshold, 2),
                above_threshold=value > base.threshold,
            )
        else:
            vitals[spec.attr] = Vital(value=value)
    return GravityMetrics(
        baseline_ready=ready,
        resting_hr=vitals["resting_hr"],
        sys_bp=vitals["sys_bp"],
        dia_bp=vitals["dia_bp"],
        exercise_min=latest.exercise_min,
        exercise_missed_days=gravity.missed_exercise_days(ctx.records),
        drifting=drifting,
    )


def _environment(ctx: RuleContext) -> EnvironmentMetrics:
    r = ctx.records[-1]
    return EnvironmentMetrics(
        co2_mmhg_1h=r.co2_mmhg_1h,
        co2_1h_limit=t.CO2_1H_LIMIT_MMHG,
        co2_mmhg_7d=r.co2_mmhg_7d,
        co2_7d_limit=t.CO2_7D_LIMIT_MMHG,
        cabin_temp_c=r.cabin_temp_c,
        temp_min_c=t.TEMP_MIN_C,
        temp_max_c=t.TEMP_MAX_C,
    )


def _mirror(ctx: RuleContext) -> MirrorMetrics:
    gap = mirror_gap.gap_series(ctx.records)[-1]
    r = ctx.records[-1]
    return MirrorMetrics(
        gap=None if gap is None else round(gap, 3),
        amber_gap=t.GAP_AMBER,
        red_gap=t.GAP_RED,
        self_rating=r.self_rating,
        pvt_mean_rt_ms=r.pvt_mean_rt,
        pvt_lapses=r.pvt_lapses,
        lapse_band=mirror_gap.lapse_band_label(r.pvt_lapses),
        baseline_sessions=t.GAP_BASELINE_SESSIONS,
    )


_BUILDERS: dict[Hazard, Callable[[RuleContext], CardMetrics]] = {
    Hazard.RADIATION: _radiation,
    Hazard.ISOLATION: _isolation,
    Hazard.DISTANCE: _distance,
    Hazard.GRAVITY: _gravity,
    Hazard.ENVIRONMENT: _environment,
    Hazard.MIRROR: _mirror,
}

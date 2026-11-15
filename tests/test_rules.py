from datetime import UTC, datetime

from app.models.crew import DailyRecord
from app.models.enums import DataSource, EventKind, Level, Mission
from app.models.space_weather import SpaceWeatherEvent
from app.rules import distance, environment, gravity, isolation, mirror_gap, radiation
from app.rules.context import RuleContext

T0 = datetime(2024, 5, 10, 0, 0, tzinfo=UTC)


def rec(day, **kw) -> DailyRecord:
    base = {
        "day": day,
        "sleep_hours": 7.5,
        "resting_hr": 62,
        "sys_bp": 118,
        "dia_bp": 76,
        "exercise_min": 45,
        "co2_mmhg_1h": 2.1,
        "co2_mmhg_7d": 1.9,
        "cabin_temp_c": 22.5,
        "loneliness_q1": 1,
        "loneliness_q2": 1,
        "loneliness_q3": 1,
        "self_rating": 7,
        "pvt_mean_rt": 285,
        "pvt_mean_speed": 3.5,
        "pvt_lapses": 3,
        "pvt_false_starts": 0,
        "dose_msv": 0.5,
    }
    return DailyRecord(**{**base, **kw})


def ctx(records, events=(), source=DataSource.LIVE, deep=False, mission=Mission.MARS) -> RuleContext:
    return RuleContext(
        day=len(records),
        now=T0,
        records=records,
        events=events,
        weather_source=source,
        weather_as_of=T0,
        deep_space_mode=deep,
        mission=mission,
    )


def event(kind, hours_ago, **kw):
    from datetime import timedelta

    return SpaceWeatherEvent(
        id=f"{kind}{hours_ago}", kind=kind, time=T0 - timedelta(hours=hours_ago), summary="x", **kw
    )


def top(alerts):
    return max(alerts, key=lambda a: a.level.rank).level


# --- Radiation ----------------------------------------------------------------
def test_sep_within_24h_is_red():
    assert top(radiation.evaluate(ctx([rec(1)], [event(EventKind.SEP, 3)]))) == Level.RED


def test_sep_older_than_24h_is_green():
    assert top(radiation.evaluate(ctx([rec(1)], [event(EventKind.SEP, 30)]))) == Level.GREEN


def test_x_flare_is_amber_but_m_flare_is_not():
    assert top(radiation.evaluate(ctx([rec(1)], [event(EventKind.FLARE, 2, class_type="X1.0")]))) == Level.AMBER
    assert top(radiation.evaluate(ctx([rec(1)], [event(EventKind.FLARE, 2, class_type="M9.0")]))) == Level.GREEN


def test_cme_is_amber():
    assert top(radiation.evaluate(ctx([rec(1)], [event(EventKind.CME, 5)]))) == Level.AMBER


def test_cumulative_dose_thresholds():
    days = lambda per_day: [rec(d, dose_msv=per_day) for d in range(1, 4)]
    assert top(radiation.evaluate(ctx(days(160)))) == Level.AMBER  # 480 mSv = 80%
    assert top(radiation.evaluate(ctx(days(190)))) == Level.RED  # 570 mSv = 95%
    assert top(radiation.evaluate(ctx([rec(1, dose_msv=100)]))) == Level.GREEN


# --- Isolation ----------------------------------------------------------------
def lonely(day, total):
    q = [1, 1, 1]
    for i in range(total - 3):
        q[i % 3] += 1
    return rec(day, loneliness_q1=q[0], loneliness_q2=q[1], loneliness_q3=q[2])


def test_isolation_bands():
    assert top(isolation.evaluate(ctx([lonely(1, 5)]))) == Level.GREEN
    assert top(isolation.evaluate(ctx([lonely(1, 6)]))) == Level.AMBER


def test_isolation_red_needs_three_days_at_7():
    assert top(isolation.evaluate(ctx([lonely(1, 7), lonely(2, 8)]))) == Level.AMBER
    assert top(isolation.evaluate(ctx([lonely(1, 7), lonely(2, 8), lonely(3, 7)]))) == Level.RED


def test_isolation_safety_concern_is_red_immediately():
    flagged = lonely(1, 4).model_copy(update={"isolation_safety_flag": True})
    a = isolation.evaluate(ctx([flagged]))[0]
    assert a.level == Level.RED and "wellbeing concern" in a.what


# --- Distance -----------------------------------------------------------------
def test_distance_amber_on_snapshot_or_deep_space():
    assert top(distance.evaluate(ctx([rec(1)]))) == Level.GREEN
    assert top(distance.evaluate(ctx([rec(1)], source=DataSource.SNAPSHOT))) == Level.AMBER
    a = next(x for x in distance.evaluate(ctx([rec(1)], deep=True)) if x.rule == "D.data_freshness")
    assert a.level == Level.AMBER and "space weather from 2024-05-10" in a.what


def with_distance(light_time_s, source=DataSource.LIVE, target="Mars") -> RuleContext:
    from dataclasses import replace

    from app.models.distance import DistanceSample

    sample = DistanceSample(
        time=T0, distance_km=light_time_s * 299_792.458, light_time_s=light_time_s, range_rate_km_s=1.0
    )
    return replace(ctx([rec(1)]), distance=sample, distance_target=target, distance_source=source, distance_as_of=T0)


def test_distance_comms_delay_uses_horizons_light_time():
    near = next(a for a in distance.evaluate(with_distance(1.3, target="Moon")) if a.rule == "D.comms_delay")
    assert near.level == Level.GREEN and "1.3 s" in near.what and "Moon" in near.what
    far = next(a for a in distance.evaluate(with_distance(1000)) if a.rule == "D.comms_delay")
    assert far.level == Level.AMBER and "16 min 40 s" in far.what and "AU" in far.what
    edge = next(a for a in distance.evaluate(with_distance(299.9)) if a.rule == "D.comms_delay")
    assert edge.level == Level.GREEN


def test_distance_freshness_flags_stale_ephemeris():
    stale = distance.evaluate(with_distance(1000, source=DataSource.SNAPSHOT))
    fresh = next(a for a in stale if a.rule == "D.data_freshness")
    assert fresh.level == Level.AMBER and "ephemeris from 2024-05-10" in fresh.what


def test_format_delay():
    assert [distance.format_delay(x) for x in (0.0227, 1.34, 59.9, 61, 1320)] == [
        "23 ms",
        "1.3 s",
        "59.9 s",
        "1 min 01 s",
        "22 min 00 s",
    ]


# --- Gravity ------------------------------------------------------------------
def baseline_days():
    return [rec(d) for d in range(1, 8)]


def test_gravity_baseline_period_is_green():
    assert top(gravity.evaluate(ctx(baseline_days()))) == Level.GREEN


def test_gravity_hr_drift_three_days_is_amber():
    recs = baseline_days() + [rec(8 + i, resting_hr=75) for i in range(3)]
    a = gravity.evaluate(ctx(recs))[0]
    assert a.level == Level.AMBER and "flagged for review" in a.what


def test_gravity_two_days_of_drift_is_not_enough():
    recs = [*baseline_days(), rec(8, resting_hr=75), rec(9, resting_hr=75)]
    assert top(gravity.evaluate(ctx(recs))) == Level.GREEN


def test_gravity_missed_exercise_amber_and_both_red():
    missed = [*baseline_days(), rec(8, exercise_min=0), rec(9, exercise_min=0)]
    assert top(gravity.evaluate(ctx(missed))) == Level.AMBER
    both = baseline_days() + [rec(8 + i, resting_hr=75, exercise_min=0) for i in range(3)]
    assert top(gravity.evaluate(ctx(both))) == Level.RED


# --- Environment --------------------------------------------------------------
def test_environment_rules():
    assert top(environment.evaluate(ctx([rec(1)]))) == Level.GREEN
    assert top(environment.evaluate(ctx([rec(1, co2_mmhg_7d=2.6)]))) == Level.AMBER
    assert top(environment.evaluate(ctx([rec(1, co2_mmhg_1h=3.2)]))) == Level.RED
    assert top(environment.evaluate(ctx([rec(1, cabin_temp_c=28)]))) == Level.AMBER
    assert top(environment.evaluate(ctx([rec(1, cabin_temp_c=17.5)]))) == Level.AMBER


# --- Mirror Gap ---------------------------------------------------------------
def test_classify_requires_consecutive_days():
    assert mirror_gap.classify([0, 1.2]) == Level.GREEN
    assert mirror_gap.classify([1.2, 1.2]) == Level.AMBER
    assert mirror_gap.classify([1.6, 1.7]) == Level.RED
    assert mirror_gap.classify([1.6, 1.2]) == Level.AMBER
    assert mirror_gap.classify([None, 2.0]) == Level.GREEN


def test_gap_positive_when_feeling_sharp_but_slow():
    recs = [rec(d) for d in range(1, 6)] + [rec(6, pvt_mean_speed=3.0), rec(7, pvt_mean_speed=3.0)]
    gaps = mirror_gap.gap_series(recs)
    assert gaps[:5] == [0.0] * 5 or all(abs(g) < 1e-9 for g in gaps[:5])
    assert gaps[5] > 1.5 and top(mirror_gap.evaluate(ctx(recs))) == Level.RED


def test_lapse_bands():
    assert [mirror_gap.lapse_band_label(n) for n in (10, 11, 19, 20)] == [
        "good",
        "reduced",
        "reduced",
        "poor",
    ]

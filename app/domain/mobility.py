"""Mobility & Balance Check scoring (pure): status per test and overall.

Each test is judged two ways: absolute limits (illustrative) and how much worse it is than the astronaut's
own first reliable check. All cut-offs are ours (illustrative), not clinical.
"""

from collections.abc import Sequence

from app.domain.prng import js_round
from app.schemas.crew import Status
from app.schemas.mobility import MobilityCheck, MobilityResult, MobilityTestResult

MIN_CONFIDENCE = 0.6  # mean pose-keypoint confidence below which a check is stored but not used
BALANCE_HOLD_MAX_S = 30.0  # single-leg stance is stopped at 30 s
BALANCE_HOLD_WATCH_S = 10.0  # hold shorter than this -> watch
BALANCE_HOLD_ALERT_S = 5.0  # hold shorter than this -> alert
SIT_STAND_WATCH_S = 12.0  # 5 sit-to-stands slower than this -> watch
SIT_STAND_ALERT_S = 15.0  # slower than this -> alert
KNEE_FLEXION_WATCH_DEG = 100.0  # squat depth shallower than this -> watch
KNEE_FLEXION_ALERT_DEG = 80.0  # shallower than this -> alert
CHANGE_WATCH = 0.25  # 25 % worse than the astronaut's first check -> watch
CHANGE_ALERT = 0.50  # 50 % worse than the first check -> alert

_RANK = {"nominal": 0, "watch": 1, "alert": 2}
_NOTE: dict[str, str] = {
    "nominal": "Within your normal range.",
    "watch": "Worse than expected: repeat the test and review.",
    "alert": "Clearly reduced: flag for flight surgeon review.",
}


def _worst(statuses: list[Status]) -> Status:
    return max(statuses, key=lambda s: _RANK[s], default="nominal")


def _worse_pct(value: float, base: float, higher_is_worse: bool) -> float:
    """% by which `value` is worse than `base` (negative = better)."""
    if base <= 0:
        return 0.0
    change = (value - base) / base if higher_is_worse else (base - value) / base
    return float(js_round(100 * change * 10) / 10)


def _relative(change_pct: float) -> Status:
    if change_pct >= 100 * CHANGE_ALERT:
        return "alert"
    if change_pct >= 100 * CHANGE_WATCH:
        return "watch"
    return "nominal"


def _absolute(value: float, watch: float, alert: float, higher_is_worse: bool) -> Status:
    if higher_is_worse:
        return "alert" if value >= alert else "watch" if value >= watch else "nominal"
    return "alert" if value < alert else "watch" if value < watch else "nominal"


def _test(
    test: str,
    label: str,
    *,
    latest: dict[str, float],
    first: dict[str, float],
    higher_is_worse: dict[str, bool],
    absolute: dict[str, Status],
    compare: bool,
) -> MobilityTestResult:
    changes = {k: _worse_pct(latest[k], first[k], higher_is_worse[k]) for k in latest} if compare else None
    statuses = [*absolute.values(), *([_relative(c) for c in changes.values()] if changes else [])]
    status = _worst(statuses)
    return MobilityTestResult(
        test=test,
        label=label,
        status=status,
        values=latest,
        baseline=first if compare else None,
        change_pct=changes,
        note=_NOTE[status],
    )


def assess(checks: Sequence[MobilityCheck]) -> MobilityResult | None:
    """Result for the latest reliable check; None when there is no reliable check. `checks` oldest first."""
    usable = [c for c in checks if c.reliable]
    if not usable:
        return None
    last = usable[-1]
    latest, first = last.measurements, usable[0].measurements
    compare = len(usable) > 1

    hold_abs: Status = (
        _absolute(latest.balance_hold_s, BALANCE_HOLD_WATCH_S, BALANCE_HOLD_ALERT_S, False)
        if latest.balance_hold_s < BALANCE_HOLD_MAX_S
        else "nominal"
    )
    tests = [
        _test(
            "balance",
            "Single-leg balance",
            latest={"balanceHoldS": latest.balance_hold_s, "swayPctHeight": latest.sway_pct_height},
            first={"balanceHoldS": first.balance_hold_s, "swayPctHeight": first.sway_pct_height},
            higher_is_worse={"balanceHoldS": False, "swayPctHeight": True},
            absolute={"balanceHoldS": hold_abs},
            compare=compare,
        ),
        _test(
            "sit_to_stand",
            "5x sit-to-stand",
            latest={"sitToStandS": latest.sit_to_stand_s},
            first={"sitToStandS": first.sit_to_stand_s},
            higher_is_worse={"sitToStandS": True},
            absolute={"sitToStandS": _absolute(latest.sit_to_stand_s, SIT_STAND_WATCH_S, SIT_STAND_ALERT_S, True)},
            compare=compare,
        ),
        _test(
            "squat_rom",
            "Squat knee bend",
            latest={"kneeFlexionDeg": latest.knee_flexion_deg},
            first={"kneeFlexionDeg": first.knee_flexion_deg},
            higher_is_worse={"kneeFlexionDeg": False},
            absolute={
                "kneeFlexionDeg": _absolute(
                    latest.knee_flexion_deg, KNEE_FLEXION_WATCH_DEG, KNEE_FLEXION_ALERT_DEG, False
                )
            },
            compare=compare,
        ),
    ]
    return MobilityResult(
        status=_worst([t.status for t in tests]),
        tests=tests,
        checks_used=len(usable),
        last_check_at=last.at,
        last_check_day=last.day,
    )


def checks_until(checks: Sequence[MobilityCheck], hour: float) -> list[MobilityCheck]:
    """Checks submitted up to `hour` (oldest first).

    Includes the current quarter hour: analysis is cached per quarter hour (and the frontend asks at
    quarter-aligned times), so a check made a minute ago must show up in the analysis already cached
    for this quarter. Safety flags and shared notes use the same lookahead.
    """
    return [c for c in checks if c.at <= hour + 0.25]


def value_text(result: MobilityResult) -> str:
    """One line for the Gravity driver, e.g. '105° squat · 9.0 s sit-to-stand · 30 s balance'."""
    v = {k: x for t in result.tests for k, x in t.values.items()}
    return (
        f"{v['kneeFlexionDeg']:.0f}° squat · {v['sitToStandS']:.1f} s sit-to-stand · {v['balanceHoldS']:.0f} s balance"
    )


def test_text(test: MobilityTestResult, values: dict[str, float]) -> str:
    """Human-readable measurement for one test (used as finding evidence)."""
    if test.test == "balance":
        return f"{values['balanceHoldS']:.0f} s hold · sway {values['swayPctHeight']:.1f}% of height"
    if test.test == "sit_to_stand":
        return f"{values['sitToStandS']:.1f} s for 5 stands"
    return f"{values['kneeFlexionDeg']:.0f}° knee bend"

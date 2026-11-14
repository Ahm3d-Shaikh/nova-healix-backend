"""Mobility & Balance Check scoring (pure): level per test and overall.

Each test is judged two ways: absolute limits (illustrative) and how much worse it is than
the astronaut's own first reliable check. Cut-offs are ours; see thresholds.py.
"""

from collections.abc import Sequence

from app.models.alert import Alert
from app.models.enums import Hazard, Level, worst
from app.models.mobility import MobilityCheck, MobilityResult, TestResult
from app.rules import thresholds as t

SRC = (
    "Single-leg stance, 5x sit-to-stand and squat depth, measured with MediaPipe Pose; "
    "cut-offs are ours (illustrative), compared with your own first check"
)
WHY = (
    "Muscle and joint deconditioning and slower balance control are known effects of reduced gravity. "
    "This check looks at movement only, not bone health."
)


def _worse_pct(value: float, base: float, higher_is_worse: bool) -> float:
    """% by which `value` is worse than `base` (negative = better)."""
    if base <= 0:
        return 0.0
    change = (value - base) / base if higher_is_worse else (base - value) / base
    return round(100 * change, 1)


def _relative_level(change_pct: float) -> Level:
    if change_pct >= 100 * t.MOBILITY_CHANGE_RED:
        return Level.RED
    if change_pct >= 100 * t.MOBILITY_CHANGE_AMBER:
        return Level.AMBER
    return Level.GREEN


def _absolute(value: float, amber: float, red: float, higher_is_worse: bool) -> Level:
    if higher_is_worse:
        return Level.RED if value >= red else Level.AMBER if value >= amber else Level.GREEN
    return Level.RED if value < red else Level.AMBER if value < amber else Level.GREEN


def _test(
    test: str,
    label: str,
    *,
    latest: dict[str, float],
    first: dict[str, float],
    higher_is_worse: dict[str, bool],
    absolute: dict[str, Level],
    compare: bool,
) -> TestResult:
    changes = {k: _worse_pct(latest[k], first[k], higher_is_worse[k]) for k in latest} if compare else None
    levels = list(absolute.values()) + ([_relative_level(c) for c in changes.values()] if changes else [])
    level = worst(levels)
    note = {
        Level.GREEN: "Within your normal range.",
        Level.AMBER: "Worse than expected: repeat the test and review.",
        Level.RED: "Clearly reduced: flag for flight surgeon review.",
    }[level]
    return TestResult(
        test=test,
        label=label,
        level=level,
        values=latest,
        baseline=first if compare else None,
        change_pct=changes,
        note=note,
    )


def assess(checks: Sequence[MobilityCheck]) -> MobilityResult | None:
    """Result for the latest reliable check; None when there is no reliable check."""
    usable = [c for c in checks if c.reliable]
    if not usable:
        return None
    latest, first = usable[-1].measurements, usable[0].measurements
    compare = len(usable) > 1

    balance = _test(
        "balance",
        "Single-leg balance",
        latest={"balance_hold_s": latest.balance_hold_s, "sway_pct_height": latest.sway_pct_height},
        first={"balance_hold_s": first.balance_hold_s, "sway_pct_height": first.sway_pct_height},
        higher_is_worse={"balance_hold_s": False, "sway_pct_height": True},
        absolute={
            "balance_hold_s": _absolute(latest.balance_hold_s, t.BALANCE_HOLD_AMBER_S, t.BALANCE_HOLD_RED_S, False)
            if latest.balance_hold_s < t.BALANCE_HOLD_MAX_S
            else Level.GREEN
        },
        compare=compare,
    )
    sit = _test(
        "sit_to_stand",
        "5x sit-to-stand",
        latest={"sit_to_stand_5x_s": latest.sit_to_stand_5x_s},
        first={"sit_to_stand_5x_s": first.sit_to_stand_5x_s},
        higher_is_worse={"sit_to_stand_5x_s": True},
        absolute={
            "sit_to_stand_5x_s": _absolute(latest.sit_to_stand_5x_s, t.SIT_STAND_AMBER_S, t.SIT_STAND_RED_S, True)
        },
        compare=compare,
    )
    squat = _test(
        "squat_rom",
        "Squat knee bend",
        latest={"knee_flexion_deg": latest.knee_flexion_deg},
        first={"knee_flexion_deg": first.knee_flexion_deg},
        higher_is_worse={"knee_flexion_deg": False},
        absolute={
            "knee_flexion_deg": _absolute(
                latest.knee_flexion_deg, t.KNEE_FLEXION_AMBER_DEG, t.KNEE_FLEXION_RED_DEG, False
            )
        },
        compare=compare,
    )
    tests = [balance, sit, squat]
    level = worst([x.level for x in tests])
    flagged = [x.label for x in tests if x.level != Level.GREEN]
    what = (
        "Mobility & Balance Check flagged: " + ", ".join(flagged) + "."
        if flagged
        else "Mobility & Balance Check within your normal range."
    )
    action = {
        Level.GREEN: "No action needed.",
        Level.AMBER: "Repeat the check tomorrow and keep up resistive exercise.",
        Level.RED: "Flag for review by flight surgeon; repeat the check and review the exercise protocol.",
    }[level]
    alert = Alert(rule="G.mobility", hazard=Hazard.GRAVITY, level=level, what=what, why=WHY, action=action, source=SRC)
    return MobilityResult(
        level=level, tests=tests, alert=alert, checks_used=len(usable), last_check_day=usable[-1].mission_day
    )

"""G - Gravity fields: cardiovascular drift flag (illustrative thresholds)."""

from collections.abc import Sequence
from dataclasses import dataclass

from app.models.alert import Alert
from app.models.crew import DailyRecord
from app.models.enums import Hazard, Level
from app.rules import mobility
from app.rules import thresholds as t
from app.rules.context import RuleContext
from app.rules.stats import mean_sd, trailing_streak

SRC = "Baseline = days 1-7 mean ± SD per astronaut; thresholds illustrative (CSA Bio-Monitor style monitoring)"
WHY = "Cardiovascular deconditioning is a known effect of altered gravity."


@dataclass(frozen=True)
class VitalSpec:
    attr: str
    label: str
    sd_floor: float


VITALS: tuple[VitalSpec, ...] = (
    VitalSpec("resting_hr", "resting HR", t.HR_SD_FLOOR),
    VitalSpec("sys_bp", "systolic BP", t.SYS_BP_SD_FLOOR),
    VitalSpec("dia_bp", "diastolic BP", t.DIA_BP_SD_FLOOR),
)


@dataclass(frozen=True)
class VitalBaseline:
    mean: float
    threshold: float  # mean + SD_MULTIPLIER * sd


def baseline_ready(records: Sequence[DailyRecord]) -> bool:
    return len(records) > t.BASELINE_DAYS


def vital_baseline(records: Sequence[DailyRecord], spec: VitalSpec) -> VitalBaseline:
    mean, sd = mean_sd([getattr(r, spec.attr) for r in records[: t.BASELINE_DAYS]], spec.sd_floor)
    return VitalBaseline(mean, mean + t.SD_MULTIPLIER * sd)


def drifting_metrics(records: Sequence[DailyRecord]) -> list[str]:
    """Labels of vitals above baseline + 2 SD for the required streak of days ending today."""
    if not baseline_ready(records):
        return []
    out = []
    for spec in VITALS:
        limit = vital_baseline(records, spec).threshold
        flags = [getattr(r, spec.attr) > limit for r in records[t.BASELINE_DAYS :]]
        if trailing_streak(flags) >= t.DRIFT_STREAK_DAYS:
            out.append(spec.label)
    return out


def missed_exercise_days(records: Sequence[DailyRecord]) -> int:
    return trailing_streak([r.exercise_min < t.MISSED_EXERCISE_MIN for r in records])


def evaluate(ctx: RuleContext) -> list[Alert]:
    """Cardiovascular drift / exercise rule, plus the Mobility & Balance Check once one has been done."""
    alerts = _cardio(ctx)
    result = mobility.assess(ctx.mobility)
    return [*alerts, result.alert] if result else alerts


def _cardio(ctx: RuleContext) -> list[Alert]:
    if not baseline_ready(ctx.records):
        return [
            Alert(
                rule="G.cardio",
                hazard=Hazard.GRAVITY,
                level=Level.GREEN,
                what=f"Building personal baseline (days 1-{t.BASELINE_DAYS}).",
                why=WHY,
                action="No action needed.",
                source=SRC,
            )
        ]

    drifting = drifting_metrics(ctx.records)
    missed = missed_exercise_days(ctx.records) >= t.MISSED_EXERCISE_DAYS

    if drifting and missed:
        level, action = Level.RED, "Flag for review by flight surgeon; resume exercise protocol today."
    elif drifting:
        level, action = Level.AMBER, "Flag for review: repeat measurements and discuss with flight surgeon."
    elif missed:
        level, action = Level.AMBER, "Resume the exercise protocol; log the reason it was missed."
    else:
        level, action = Level.GREEN, "No action needed."

    parts = []
    if drifting:
        parts.append(f"{', '.join(drifting)} above baseline + {t.SD_MULTIPLIER:g} SD for ≥{t.DRIFT_STREAK_DAYS} days")
    if missed:
        parts.append(f"exercise missed {t.MISSED_EXERCISE_DAYS}+ consecutive days")
    what = (
        "Readings flagged for review: " + "; ".join(parts) + "."
        if parts
        else "Heart rate, blood pressure and exercise within personal baseline."
    )
    return [Alert(rule="G.cardio", hazard=Hazard.GRAVITY, level=level, what=what, why=WHY, action=action, source=SRC)]

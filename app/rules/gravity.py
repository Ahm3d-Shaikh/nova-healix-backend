"""G — Gravity fields: cardiovascular drift flag (illustrative thresholds)."""

from app.models.alert import Alert
from app.models.crew import DailyRecord
from app.models.enums import Hazard, Level
from app.rules.context import RuleContext
from app.rules.stats import mean_sd, trailing_streak

BASELINE_DAYS = 7
SD_MULTIPLIER = 2.0
STREAK_DAYS = 3
MISSED_EXERCISE_MIN = 10  # below this = "missed" (illustrative)
MISSED_EXERCISE_DAYS = 2
# SD floors so a quiet baseline cannot trigger on ordinary noise (illustrative)
METRICS = {
    "resting_hr": ("resting HR", "bpm", 1.5),
    "sys_bp": ("systolic BP", "mmHg", 3.0),
    "dia_bp": ("diastolic BP", "mmHg", 2.0),
}
SRC = "Baseline = days 1-7 mean ± SD per astronaut; thresholds illustrative (CSA Bio-Monitor style monitoring)"
WHY = "Cardiovascular deconditioning is a known effect of altered gravity."


def evaluate(ctx: RuleContext) -> list[Alert]:
    if len(ctx.records) <= BASELINE_DAYS:
        return [Alert(
            rule="G.cardio", hazard=Hazard.GRAVITY, level=Level.GREEN,
            what=f"Building personal baseline (days 1-{BASELINE_DAYS}).",
            why=WHY, action="No action needed.", source=SRC,
        )]

    drifting = _drifting_metrics(ctx.records)
    missed = _missed_exercise(ctx.records)

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
        parts.append(f"{', '.join(drifting)} above baseline + {SD_MULTIPLIER:g} SD for ≥{STREAK_DAYS} days")
    if missed:
        parts.append(f"exercise missed {MISSED_EXERCISE_DAYS}+ consecutive days")
    what = "Readings flagged for review: " + "; ".join(parts) + "." if parts else \
        "Heart rate, blood pressure and exercise within personal baseline."
    return [Alert(rule="G.cardio", hazard=Hazard.GRAVITY, level=level, what=what,
                  why=WHY, action=action, source=SRC)]


def _drifting_metrics(records: list[DailyRecord]) -> list[str]:
    base = records[:BASELINE_DAYS]
    out = []
    for attr, (label, _unit, floor) in METRICS.items():
        mu, sd = mean_sd([getattr(r, attr) for r in base], floor)
        flags = [getattr(r, attr) > mu + SD_MULTIPLIER * sd for r in records[BASELINE_DAYS:]]
        if trailing_streak(flags) >= STREAK_DAYS:
            out.append(label)
    return out


def _missed_exercise(records: list[DailyRecord]) -> bool:
    return trailing_streak([r.exercise_min < MISSED_EXERCISE_MIN for r in records]) >= MISSED_EXERCISE_DAYS

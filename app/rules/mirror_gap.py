"""Mirror Gap - does how I feel match how I perform?

gap = z_self - z_performance, both z-scored against the person's first 5 sessions
(performance = mean 1/RT; higher = better). Positive gap = feels sharper than
performing. Cut-offs are ours (illustrative).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.models.alert import Alert
from app.models.crew import DailyRecord
from app.models.enums import Hazard, Level
from app.rules import thresholds as t
from app.rules.context import RuleContext
from app.rules.stats import mean_sd, zscore

SRC = (
    "PVT-B (Basner et al., 2011); lapse bands Basner & Rubinstein 2011; "
    "z-score gap and cut-offs are ours (illustrative)"
)
AMBER_MESSAGE = "You feel sharper than you're performing. Get a crewmate cross-check before critical tasks."


@dataclass(frozen=True)
class Baseline:
    self_mean: float
    self_sd: float
    speed_mean: float
    speed_sd: float

    @classmethod
    def from_sessions(cls, self_ratings: Sequence[float], speeds: Sequence[float]) -> "Baseline":
        n = t.GAP_BASELINE_SESSIONS
        sm, ss = mean_sd(self_ratings[:n], t.SELF_RATING_SD_FLOOR)
        pm, ps = mean_sd(speeds[:n], t.SPEED_SD_FLOOR)
        return cls(sm, ss, pm, ps)

    def z_self(self, rating: float) -> float:
        return zscore(rating, self.self_mean, self.self_sd)

    def z_performance(self, speed: float) -> float:
        return zscore(speed, self.speed_mean, self.speed_sd)

    def gap(self, rating: float, speed: float) -> float:
        return self.z_self(rating) - self.z_performance(speed)


def baseline_for(records: Sequence[DailyRecord]) -> Baseline | None:
    if len(records) < t.GAP_BASELINE_SESSIONS:
        return None
    return Baseline.from_sessions([r.self_rating for r in records], [r.pvt_mean_speed for r in records])


def gap_series(records: Sequence[DailyRecord]) -> list[float | None]:
    base = baseline_for(records)
    if base is None:
        return [None] * len(records)
    return [base.gap(r.self_rating, r.pvt_mean_speed) for r in records]


def classify(gaps: Sequence[float | None]) -> Level:
    recent = [g for g in gaps if g is not None][-t.GAP_CONSECUTIVE_DAYS :]
    if len(recent) < t.GAP_CONSECUTIVE_DAYS:
        return Level.GREEN
    if all(g > t.GAP_RED for g in recent):
        return Level.RED
    if all(g > t.GAP_AMBER for g in recent):
        return Level.AMBER
    return Level.GREEN


def lapse_band_label(lapses: int) -> str:
    if lapses < t.LAPSE_BAND_REDUCED:
        return "good"
    return "reduced" if lapses < t.LAPSE_BAND_POOR else "poor"


def make_alert(level: Level, gap: float | None, lapses: int | None = None) -> Alert:
    band = f" PVT lapses: {lapses} ({lapse_band_label(lapses)})." if lapses is not None else ""
    if gap is None:
        what = f"Not enough sessions yet for a baseline (need {t.GAP_BASELINE_SESSIONS})."
    else:
        what = f"Mirror gap {gap:+.2f} (self-rating vs reaction-test performance).{band}"
    if level == Level.GREEN:
        action = "No action needed."
    elif level == Level.AMBER:
        action = AMBER_MESSAGE
    else:
        action = AMBER_MESSAGE + " Do not rely on self-assessment today."
    return Alert(
        rule="MIRROR.gap",
        hazard=Hazard.MIRROR,
        level=level,
        what=what,
        why="When self-judgment and measured performance diverge, fatigue may be going unnoticed.",
        action=action,
        source=SRC,
    )


def evaluate(ctx: RuleContext) -> list[Alert]:
    gaps = gap_series(ctx.records)
    latest = gaps[-1] if gaps else None
    lapses = ctx.records[-1].pvt_lapses if ctx.records else None
    return [make_alert(classify(gaps), latest, lapses)]

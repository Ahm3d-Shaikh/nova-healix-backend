"""Shared helpers for the scoring engine (frontend `engine/context.ts`)."""

import math
from dataclasses import dataclass

from app.domain.link import LinkState
from app.domain.metrics import METRICS
from app.domain.prng import clamp, js_round
from app.domain.stats import mean
from app.domain.store import MissionData
from app.schemas.mission import MissionEvent
from app.schemas.telemetry import Baseline, CheckIn

H_PER_DAY = 24


@dataclass(frozen=True)
class EngineContext:
    db: MissionData
    hour: float  # evaluation time, mission hour
    link: LinkState
    career_limit_msv: float

    def at(self, hour: float) -> "EngineContext":
        return EngineContext(self.db, hour, self.link, self.career_limit_msv)


def half_band(b: Baseline) -> float:
    """Half-width of a baseline band."""
    return max(1e-6, (b.high - b.low) / 2)


def z_low(x: float, b: Baseline) -> float:
    """Standardised deviation below the personal mean (0 = at the mean, 1 = at the band edge)."""
    return (b.mean - x) / half_band(b)


def z_high(x: float, b: Baseline) -> float:
    return (x - b.mean) / half_band(b)


def contrib(z: float, gain: float = 45) -> float:
    """Map a z deviation onto a 0-100 contribution. Band edge is about 45."""
    return clamp(z * gain, 0, 100)


def recent_mean(ctx: EngineContext, crew_id: str, metric: str, days: float) -> float:
    """Mean over `days` ending at ctx.hour. Hourly vitals exclude exercise/EVA hours."""
    window = ctx.db.series(crew_id, metric).slice(ctx.hour - days * H_PER_DAY, ctx.hour)
    pairs = window.pairs()
    if METRICS[metric].cadence == "hourly":
        pairs = [(t, v) for t, v in pairs if not ctx.db.is_active(crew_id, t)]
    return mean([v for _, v in pairs])


def latest(ctx: EngineContext, crew_id: str, metric: str) -> tuple[float, float] | None:
    return ctx.db.series(crew_id, metric).last_at(ctx.hour)


def recent_check_ins(ctx: EngineContext, crew_id: str, days: float) -> list[CheckIn]:
    return [c for c in ctx.db.check_ins(crew_id) if ctx.hour - days * H_PER_DAY < c.at <= ctx.hour]


def symptom_count(check_ins: list[CheckIn], symptom: str) -> int:
    return sum(1 for c in check_ins if symptom in c.symptoms)


def missed_check_in_days(ctx: EngineContext, crew_id: str, days: int) -> list[int]:
    """Completed days in the last `days` with no check-in (today excluded)."""
    today = math.floor(ctx.hour / H_PER_DAY) + 1
    have = {c.day for c in ctx.db.check_ins(crew_id) if c.at <= ctx.hour}
    return [d for d in range(today - days, today) if d >= 1 and d not in have]


def next_eva_for(ctx: EngineContext, crew_id: str) -> MissionEvent | None:
    evas = [e for e in ctx.db.events() if e.kind == "eva" and crew_id in e.crew_ids and e.start > ctx.hour]
    return min(evas, key=lambda e: e.start) if evas else None


def combine(parts: list[tuple[float, float]]) -> int:
    """Combine (contribution, weight) pairs: dominated by the worst driver, tempered by the rest."""
    mx = max([0.0, *(c for c, _ in parts)])
    wsum = sum(w for _, w in parts) or 1.0
    wmean = sum(c * w for c, w in parts) / wsum
    return int(js_round(clamp(0.4 * mx + 0.6 * wmean, 0, 100)))


def score_to_status(score: float) -> str:
    """Hazard score (0-100) to status level."""
    if score >= 70:
        return "alert"
    if score >= 40:
        return "watch"
    return "nominal"

"""Scores Mirror Gap test submissions and keeps their history (in memory)."""

from datetime import UTC, datetime
from statistics import mean

from app.core.errors import NoValidResponsesError
from app.models.crew import DailyRecord
from app.models.enums import Level
from app.models.mirror_gap import (
    LapseBand,
    MirrorGapHistory,
    MirrorGapHistoryItem,
    MirrorGapResult,
    MirrorGapSubmission,
    TestMode,
)
from app.rules import mirror_gap as rule
from app.rules import thresholds as t
from app.services.crew_service import CrewService
from app.services.store import InMemoryStore


class MirrorGapService:
    def __init__(self, crew: CrewService) -> None:
        self._crew = crew
        self._submitted: InMemoryStore[MirrorGapResult] = InMemoryStore()

    def submit(self, astronaut_id: str, body: MirrorGapSubmission, day: int) -> MirrorGapResult:
        """Score a test taken on mission `day`; the gap is judged against the days before it."""
        astro = self._crew.astronaut(astronaut_id)
        times = body.reaction_times_ms
        valid = [ms for ms in times if ms >= t.PVT_FALSE_START_MS]
        if not valid:
            raise NoValidResponsesError
        lapses = sum(1 for ms in valid if ms >= t.PVT_LAPSE_MS)
        mean_speed = mean(1000 / ms for ms in valid)
        validated = body.mode == TestMode.PVT_B_3MIN

        sim = self._crew.records(astro.id)
        base = rule.baseline_for(sim)
        z_self = z_perf = gap = None
        level = Level.GREEN
        if base is not None:
            z_self, z_perf = base.z_self(body.self_rating), base.z_performance(mean_speed)
            gap = z_self - z_perf
            prior = [r.gap for r in self._submitted.all(astro.id)]
            level = rule.classify([*rule.gap_series(self._prior_sim(sim, day)), *prior, gap])

        result = MirrorGapResult(
            mode=body.mode,
            validated=validated,
            self_rating=body.self_rating,
            responses=len(valid),
            mean_rt_ms=round(mean(valid), 1),
            mean_speed=round(mean_speed, 3),
            lapses=lapses,
            false_starts=len(times) - len(valid),
            lapse_band=LapseBand(rule.lapse_band_label(lapses)) if validated else None,
            z_self=_round(z_self),
            z_performance=_round(z_perf),
            gap=_round(gap),
            level=level,
            alert=rule.make_alert(level, gap, lapses if validated else None),
            created_at=datetime.now(UTC),
        )
        self._submitted.add(astro.id, result)
        return result

    def history(self, astronaut_id: str) -> MirrorGapHistory:
        astro = self._crew.astronaut(astronaut_id)
        sim = self._crew.records(astro.id)
        gaps = rule.gap_series(sim)
        items = [
            MirrorGapHistoryItem(
                day=r.day,
                source="simulated",
                self_rating=r.self_rating,
                mean_rt_ms=r.pvt_mean_rt,
                lapses=r.pvt_lapses,
                gap=_round(g),
                level=rule.classify(gaps[: i + 1]),
            )
            for i, (r, g) in enumerate(zip(sim, gaps, strict=True))
        ]
        items += [
            MirrorGapHistoryItem(
                day=None,
                source="submitted",
                self_rating=s.self_rating,
                mean_rt_ms=s.mean_rt_ms,
                lapses=s.lapses,
                gap=s.gap,
                level=s.level,
            )
            for s in self._submitted.all(astro.id)
        ]
        return MirrorGapHistory(astronaut_id=astro.id, baseline_sessions=t.GAP_BASELINE_SESSIONS, items=items)

    @staticmethod
    def _prior_sim(sim: list[DailyRecord], day: int) -> list[DailyRecord]:
        return sim[: max(0, day - 1)]


def _round(x: float | None) -> float | None:
    return None if x is None else round(x, 3)

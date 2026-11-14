"""Scores Mirror Gap test submissions and keeps their history (in memory)."""

from datetime import datetime, timezone
from statistics import mean

from app.models.crew import DailyRecord
from app.models.enums import Level
from app.models.mirror_gap import (
    LapseBand, MirrorGapHistory, MirrorGapHistoryItem, MirrorGapResult,
    MirrorGapSubmission, TestMode,
)
from app.rules import mirror_gap as rule
from app.services.crew_service import CrewService

LAPSE_MS = 355  # PVT-B lapse threshold (Basner et al., 2011)
FALSE_START_MS = 100


class NoValidResponses(ValueError):
    pass


class MirrorGapService:
    def __init__(self, crew: CrewService):
        self._crew = crew
        self._submitted: dict[str, list[MirrorGapResult]] = {}

    def _prior_sim(self, astronaut_id: str) -> list[DailyRecord]:
        """Simulated sessions before the current mission day."""
        day = self._crew.resolve_day(None)
        return self._crew.records(astronaut_id)[: max(0, day - 1)]

    def submit(self, astronaut_id: str, body: MirrorGapSubmission) -> MirrorGapResult:
        astro = self._crew.astronaut(astronaut_id)
        times = body.reaction_times_ms
        false_starts = sum(1 for t in times if t < FALSE_START_MS)
        valid = [t for t in times if t >= FALSE_START_MS]
        if not valid:
            raise NoValidResponses("every response was a false start (<100 ms)")
        lapses = sum(1 for t in valid if t >= LAPSE_MS)
        mean_rt = mean(valid)
        mean_speed = mean(1000 / t for t in valid)
        validated = body.mode == TestMode.PVT_B_3MIN

        sim = self._crew.records(astro.id)
        base = rule.baseline_for(sim)
        prior = self._submitted.get(astro.id, [])
        z_self = z_perf = gap = None
        level = Level.GREEN
        if base is not None:
            z_self, z_perf = base.z_self(body.self_rating), base.z_performance(mean_speed)
            gap = z_self - z_perf
            prev_gaps = rule.gap_series(self._prior_sim(astro.id)) + [r.gap for r in prior]
            level = rule.classify([*prev_gaps, gap])

        result = MirrorGapResult(
            mode=body.mode, validated=validated, self_rating=body.self_rating,
            responses=len(valid), mean_rt_ms=round(mean_rt, 1), mean_speed=round(mean_speed, 3),
            lapses=lapses, false_starts=false_starts,
            lapse_band=LapseBand(rule.lapse_band_label(lapses)) if validated else None,
            z_self=_r(z_self), z_performance=_r(z_perf), gap=_r(gap), level=level,
            alert=rule.make_alert(level, gap, lapses if validated else None),
            created_at=datetime.now(timezone.utc),
        )
        self._submitted.setdefault(astro.id, []).append(result)
        return result

    def history(self, astronaut_id: str) -> MirrorGapHistory:
        astro = self._crew.astronaut(astronaut_id)
        sim = self._crew.records(astro.id)
        gaps = rule.gap_series(sim)
        items = [
            MirrorGapHistoryItem(
                day=r.day, source="simulated", self_rating=r.self_rating, mean_rt_ms=r.pvt_mean_rt,
                lapses=r.pvt_lapses, gap=_r(g), level=rule.classify(gaps[: i + 1]),
            )
            for i, (r, g) in enumerate(zip(sim, gaps))
        ]
        items += [
            MirrorGapHistoryItem(
                day=None, source="submitted", self_rating=s.self_rating, mean_rt_ms=s.mean_rt_ms,
                lapses=s.lapses, gap=s.gap, level=s.level,
            )
            for s in self._submitted.get(astro.id, [])
        ]
        return MirrorGapHistory(astronaut_id=astro.id, baseline_sessions=rule.BASELINE_SESSIONS, items=items)


def _r(x: float | None) -> float | None:
    return None if x is None else round(x, 3)

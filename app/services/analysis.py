"""Hazard scores, findings, crew summaries and metric interpretation, cached per quarter hour."""

import math
from dataclasses import dataclass

from app.core.errors import UnknownAstronautError, UnknownHazardError, UnknownMetricError
from app.domain.engine.context import EngineContext
from app.domain.engine.hazards import assess_hazards, hazard_history
from app.domain.engine.insights import SEVERITY_RANK, detect_insights
from app.domain.engine.interpret import interpret_metric
from app.domain.link import link_state_at
from app.domain.metrics import METRICS
from app.domain.mission_plan import CAREER_DOSE_LIMIT_MSV, hour_to_day
from app.domain.store import MissionData
from app.schemas.assessment import HazardAssessment, Insight, MetricInterpretation
from app.schemas.crew import CrewSummary, NextEvent
from app.schemas.mission import HAZARD_KEYS, HazardKey
from app.schemas.telemetry import Sample
from app.services.clock import MissionClock, Trajectory


@dataclass
class _Analysis:
    hazards: list[HazardAssessment]
    insights: list[Insight]


def _worst(statuses: list[str]) -> str:
    rank = {"nominal": 0, "watch": 1, "alert": 2}
    return max(statuses, key=lambda s: rank[s], default="nominal")


class AnalysisService:
    def __init__(self, data: MissionData, clock: MissionClock, trajectory: Trajectory) -> None:
        self._data = data
        self._clock = clock
        self._trajectory = trajectory
        self._cache: dict[tuple[float, int, bool], _Analysis] = {}

    def _ctx(self, at: float, autonomous: bool) -> EngineContext:
        return EngineContext(self._data, at, link_state_at(self._trajectory.au, at, autonomous), CAREER_DOSE_LIMIT_MSV)

    def _analyze(self, at: float | None, autonomous: bool) -> tuple[float, _Analysis]:
        hour = self._clock.clamp(at)
        key = (math.floor(hour * 4) / 4, self._data.version, autonomous)
        cached = self._cache.get(key)
        if cached is None:
            ctx = self._ctx(hour, autonomous)
            cached = _Analysis(assess_hazards(ctx), self._with_resolutions(detect_insights(ctx)))
            if len(self._cache) > 400:
                self._cache.clear()
            self._cache[key] = cached
        return hour, cached

    def _with_resolutions(self, insights: list[Insight]) -> list[Insight]:
        """Mark resolved findings; one that got more severe since it was resolved is active again."""
        out: list[Insight] = []
        for i in insights:
            r = self._data.resolution(i.id)
            if r is None:
                out.append(i)
            elif SEVERITY_RANK[i.severity] > SEVERITY_RANK[r.severity]:
                out.append(i.model_copy(update={"reopened": True}))
            else:
                out.append(i.model_copy(update={"resolution": r}))
        return out

    def hazards(self, at: float | None, autonomous: bool) -> list[HazardAssessment]:
        return self._analyze(at, autonomous)[1].hazards

    def insights(self, at: float | None, autonomous: bool) -> list[Insight]:
        return self._analyze(at, autonomous)[1].insights

    def hazard_history(
        self, hazard: str, crew_id: str, from_day: int, at: float | None, autonomous: bool
    ) -> list[Sample]:
        if hazard not in HAZARD_KEYS:
            raise UnknownHazardError(hazard)
        if self._data.astronaut(crew_id) is None:
            raise UnknownAstronautError(crew_id)
        hour = self._clock.clamp(at)
        return hazard_history(self._ctx(hour, autonomous), hazard, crew_id, from_day, hour_to_day(hour))

    def crew_summaries(self, at: float | None, autonomous: bool) -> list[CrewSummary]:
        hour, a = self._analyze(at, autonomous)
        today = hour_to_day(hour)
        out: list[CrewSummary] = []
        for astro in self._data.crew():
            hz = [h.status for h in a.hazards if h.crew_id == astro.id]
            ins = [
                ("nominal" if i.severity == "info" else i.severity)
                for i in a.insights
                if i.crew_id == astro.id and not i.resolution
            ]
            ci = next((c for c in self._data.check_ins(astro.id) if c.day == today and c.at <= hour), None)
            upcoming = sorted(
                (e for e in self._data.events() if e.start > hour and (not e.crew_ids or astro.id in e.crew_ids)),
                key=lambda e: e.start,
            )
            nxt = upcoming[0] if upcoming else None
            out.append(
                CrewSummary(
                    crew_id=astro.id,
                    status=_worst([*hz, *ins]),
                    check_in_hour=ci.at if ci else None,
                    next_event=NextEvent(label=nxt.label.split(" ")[0], day=hour_to_day(nxt.start)) if nxt else None,
                )
            )
        return out

    def interpret(self, crew_id: str, metric: str, at: float | None, autonomous: bool) -> MetricInterpretation:
        if self._data.astronaut(crew_id) is None:
            raise UnknownAstronautError(crew_id)
        if metric not in METRICS:
            raise UnknownMetricError(metric)
        hour = self._clock.clamp(at)
        ctx = self._ctx(hour, autonomous)
        result = interpret_metric(ctx, crew_id, metric)
        return result


__all__ = ["AnalysisService", "HazardKey"]

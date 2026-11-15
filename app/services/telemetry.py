"""Series, baselines, live vitals, check-ins and the timeline (read side of the data)."""

import random

from app.core.errors import UnknownAstronautError, UnknownMetricError
from app.domain.metrics import METRICS, VITAL_KEYS
from app.domain.prng import round_to
from app.domain.stats import Series, downsample
from app.domain.store import MissionData
from app.schemas.mission import MissionEvent
from app.schemas.telemetry import Baseline, CheckIn, LiveVitals, Sample
from app.services.clock import MissionClock

_LIVE_JITTER = {"hr": 1.2, "hrv": 2.2, "spo2": 0.25, "coreTemp": 0.02, "bpSys": 1.4, "bpDia": 1.0, "resp": 0.4}


class TelemetryService:
    def __init__(self, data: MissionData, clock: MissionClock) -> None:
        self._data = data
        self._clock = clock
        self._rng = random.Random()  # noqa: S311  # live vitals jitter only; not part of the stored data

    def _crew(self, crew_id: str) -> str:
        if self._data.astronaut(crew_id) is None:
            raise UnknownAstronautError(crew_id)
        return crew_id

    @staticmethod
    def _metric(metric: str) -> str:
        if metric not in METRICS:
            raise UnknownMetricError(metric)
        return metric

    def series(self, crew_id: str, metric: str, start: float, end: float, bucket: float = 1) -> list[Sample]:
        self._crew(crew_id)
        self._metric(metric)
        window = self._data.series(crew_id, metric).slice(start, min(end, self._clock.now_hour()))
        return [Sample(t=t, v=v) for t, v in downsample(window, bucket).pairs()]

    def baseline(self, crew_id: str, metric: str) -> Baseline | None:
        self._crew(crew_id)
        self._metric(metric)
        return self._data.baseline(crew_id, metric)

    def live(self, crew_id: str) -> LiveVitals:
        self._crew(crew_id)
        t = self._clock.now_hour()
        values: dict[str, float] = {}
        for k in VITAL_KEYS:
            s: Series = self._data.series(crew_id, k)
            i = min(len(s) - 2, max(0, s.lower_bound(t) - 1))
            a_t, a_v, b_t, b_v = s.t[i], s.v[i], s.t[i + 1], s.v[i + 1]
            f = max(0.0, min(1.0, (t - a_t) / ((b_t - a_t) or 1)))
            jitter = (self._rng.random() - 0.5) * 2 * _LIVE_JITTER.get(k, 0)
            values[k] = a_v + (b_v - a_v) * f + jitter
        if "spo2" in values:
            values["spo2"] = min(100.0, values["spo2"])
        return LiveVitals(crew_id=crew_id, t=t, values={k: round_to(v, 3) for k, v in values.items()})

    def check_ins(self, crew_id: str, start: float, end: float) -> list[CheckIn]:
        self._crew(crew_id)
        return [c for c in self._data.check_ins(crew_id) if start <= c.at <= end]

    def timeline(self, crew_id: str, start: float, end: float) -> list[MissionEvent]:
        """Events overlapping [start, end] that affect this astronaut, plus their exercise sessions."""
        self._crew(crew_id)
        events = [
            e
            for e in self._data.events()
            if e.end >= start and e.start <= end and (not e.crew_ids or crew_id in e.crew_ids)
        ]
        exercise = [
            MissionEvent(
                id=f"ex-{crew_id}-{s.day}",
                kind="exercise",
                label="Exercise" if s.done else "Exercise missed",
                missed=not s.done,
                start=s.start,
                end=s.end,
                crew_ids=[crew_id],
                hazards=["gravity"],
            )
            for s in self._data.exercise(crew_id)
            if s.end >= start and s.start <= end
        ]
        return sorted([*events, *exercise], key=lambda e: e.start)

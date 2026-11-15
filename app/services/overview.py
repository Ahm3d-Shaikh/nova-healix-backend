"""Views that combine the core data: Earth distance, a one-call dashboard and the active alerts."""

from app.core.reference import DISCLAIMER
from app.domain.link import link_state_at
from app.domain.mission_plan import LIGHT_SECONDS_PER_AU, MISSION_DURATION_DAYS, hour_to_day
from app.domain.store import MissionData
from app.nasa.service import KM_PER_AU
from app.schemas.assessment import Insight
from app.schemas.overview import Dashboard, DashboardCrew, DistancePoint, DistanceResponse, Link
from app.services.analysis import AnalysisService
from app.services.clock import MissionClock, Trajectory

LOOKBACK_H = 24


def _active(insights: list[Insight]) -> list[Insight]:
    return [i for i in insights if i.resolution is None]


class OverviewService:
    def __init__(
        self, data: MissionData, clock: MissionClock, trajectory: Trajectory, analysis: AnalysisService
    ) -> None:
        self._data = data
        self._clock = clock
        self._trajectory = trajectory
        self._analysis = analysis

    def distance(self) -> DistanceResponse:
        """Earth-ship distance and one-way signal delay at the start of every mission day."""
        points = [
            DistancePoint(
                day=day, distance_km=round(au * KM_PER_AU, 1), light_time_s=round(au * LIGHT_SECONDS_PER_AU, 3)
            )
            for day, au in enumerate(self._trajectory.au[: MISSION_DURATION_DAYS + 1], start=1)
        ]
        return DistanceResponse(
            mission="mars",
            target="Mars",
            source=self._trajectory.source,
            as_of=self._trajectory.as_of,
            duration_days=MISSION_DURATION_DAYS,
            days=points,
        )

    def alerts(self, at: float | None, autonomous: bool) -> list[Insight]:
        """Active (unresolved) findings at watch or alert severity, most urgent first."""
        return [i for i in _active(self._analysis.insights(at, autonomous)) if i.severity != "info"]

    def dashboard(self, at: float | None, autonomous: bool) -> Dashboard:
        hour = self._clock.clamp(at)
        insights = _active(self._analysis.insights(hour, autonomous))
        hazards = self._analysis.hazards(hour, autonomous)
        summaries = {s.crew_id: s for s in self._analysis.crew_summaries(hour, autonomous)}
        link = link_state_at(self._trajectory.au, hour, autonomous)
        return Dashboard(
            disclaimer=DISCLAIMER,
            mission_hour=round(hour, 3),
            day=hour_to_day(hour),
            duration_days=MISSION_DURATION_DAYS,
            link=Link(
                mode=link.mode, delay_seconds=round(link.delay_seconds, 3), distance_au=round(link.distance_au, 6)
            ),
            recent_space_events=[
                e for e in self._data.events() if e.source is not None and hour - LOOKBACK_H < e.start <= hour
            ],
            crew=[
                DashboardCrew(
                    astronaut=a,
                    summary=summaries[a.id],
                    hazards=[h for h in hazards if h.crew_id == a.id],
                    insights=[i for i in insights if i.crew_id == a.id],
                )
                for a in self._data.crew()
            ],
            crew_wide_insights=[i for i in insights if i.crew_id is None],
        )

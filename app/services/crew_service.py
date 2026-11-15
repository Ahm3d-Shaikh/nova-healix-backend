"""Assembles crew records, space weather and rules into assessments."""

from dataclasses import dataclass, field
from datetime import timedelta

from app.core.errors import UnknownAstronautError
from app.core.reference import DISCLAIMER
from app.core.timeline import MissionTimeline
from app.models.alert import CrewAlert
from app.models.crew import (
    Astronaut,
    AstronautSummary,
    CardStatus,
    CrewDetail,
    DailyRecord,
    DashboardCrew,
    GapPoint,
)
from app.models.dashboard import DashboardResponse, DistanceStatus, SpaceWeatherStatus
from app.models.distance import DistanceData, DistancePoint, DistanceResponse
from app.models.enums import EventKind
from app.models.isolation import LonelinessAssessment
from app.models.mobility import MobilityCheck
from app.models.settings import MissionSettings, MissionSettingsResponse
from app.models.space_weather import MissionEvent, SpaceWeatherData, SpaceWeatherEvent
from app.repositories.isolation import IsolationRepository
from app.repositories.mobility import MobilityRepository
from app.rules import engine, mirror_gap
from app.rules import thresholds as t
from app.rules.context import RuleContext
from app.services.distance_service import DistanceService
from app.services.settings_service import SettingsService
from app.services.space_weather_service import SpaceWeatherService

HAZARD_EVENT_KINDS = (EventKind.SEP, EventKind.FLARE, EventKind.CME, EventKind.GEOSTORM)

# astronaut id -> mission day -> latest reliable AI check-in for that day
Overlays = dict[str, dict[int, LonelinessAssessment]]


@dataclass(frozen=True)
class _Inputs:
    """Everything loaded once per request; assessments below are pure."""

    day: int
    weather: SpaceWeatherData
    distance: DistanceData
    settings: MissionSettings
    overlays: Overlays = field(default_factory=dict)
    mobility: dict[str, list[MobilityCheck]] = field(default_factory=dict)  # astronaut id -> reliable checks


class CrewService:
    def __init__(
        self,
        roster: list[Astronaut],
        records: dict[str, list[DailyRecord]],
        timeline: MissionTimeline,
        *,
        weather: SpaceWeatherService,
        settings: SettingsService,
        distance: DistanceService,
        isolation: IsolationRepository,
        mobility: MobilityRepository,
    ) -> None:
        self._roster = {a.id: a for a in roster}
        self._records = records
        self.timeline = timeline
        self._weather = weather
        self._settings = settings
        self._distance = distance
        self._isolation = isolation
        self._mobility = mobility

    # -- lookups ---------------------------------------------------------------
    def astronaut(self, astronaut_id: str) -> Astronaut:
        try:
            return self._roster[astronaut_id.upper()]
        except KeyError:
            raise UnknownAstronautError(astronaut_id) from None

    def records(self, astronaut_id: str) -> list[DailyRecord]:
        return self._records[self.astronaut(astronaut_id).id]

    async def resolve_day(self, day: int | None) -> int:
        """Explicit day, else the saved 'current day'. Raises InvalidDayError when out of range."""
        return self._resolve(day, await self._settings.get())

    def _resolve(self, day: int | None, settings: MissionSettings) -> int:
        return self.timeline.validate(settings.current_day if day is None else day)

    # -- inputs (all I/O happens here) ---------------------------------------------------
    async def _inputs(self, day: int | None) -> _Inputs:
        settings = await self._settings.get()
        resolved = self._resolve(day, settings)
        return _Inputs(
            day=resolved,
            weather=await self._weather.get(settings.deep_space_mode),
            distance=await self._distance.get(settings.mission, settings.deep_space_mode),
            settings=settings,
            overlays=await self._overlays(),
            mobility=await self._mobility_checks(),
        )

    async def _overlays(self) -> Overlays:
        out: Overlays = {}
        for a in await self._isolation.assessments():  # oldest first, so later check-ins win
            if a.reliable:
                out.setdefault(a.astronaut_id, {})[a.mission_day] = a
        return out

    async def _mobility_checks(self) -> dict[str, list[MobilityCheck]]:
        out: dict[str, list[MobilityCheck]] = {}
        for c in await self._mobility.checks():  # oldest first
            if c.reliable:
                out.setdefault(c.astronaut_id, []).append(c)
        return out

    def _records_upto(self, astro_id: str, day: int, overlays: Overlays) -> list[DailyRecord]:
        """Records for days 1..day with AI check-in scores applied over the simulated questionnaire."""
        by_day = overlays.get(astro_id, {})
        out = []
        for rec in self._records[astro_id][:day]:
            a = by_day.get(rec.day)
            r = rec
            if a is not None:
                r = rec.model_copy(
                    update={
                        "loneliness_q1": a.q1,
                        "loneliness_q2": a.q2,
                        "loneliness_q3": a.q3,
                        "loneliness_source": "ai_checkin",
                        "isolation_safety_flag": a.safety_concern,
                    }
                )
            out.append(r)
        return out

    async def loneliness_series(self, astronaut_id: str, upto_day: int) -> list[int]:
        """Daily loneliness totals for days 1..upto_day, AI check-ins included."""
        astro = self.astronaut(astronaut_id)
        return [r.loneliness_total for r in self._records_upto(astro.id, max(0, upto_day), await self._overlays())]

    # -- core assessment (pure, no I/O) -----------------------------------------
    def _ctx(self, astro: Astronaut, day: int, inp: _Inputs) -> RuleContext:
        now = self.timeline.day_end(day)
        return RuleContext(
            day=day,
            now=now,
            records=self._records_upto(astro.id, day, inp.overlays),
            events=inp.weather.events,
            weather_source=inp.weather.source,
            weather_as_of=inp.weather.data_as_of,
            deep_space_mode=inp.settings.deep_space_mode,
            mission=inp.settings.mission,
            distance=inp.distance.at(now),
            distance_target=inp.distance.target_name,
            distance_source=inp.distance.source,
            distance_as_of=inp.distance.data_as_of,
            mobility=[c for c in inp.mobility.get(astro.id, []) if c.mission_day <= day],
        )

    def _cards(self, astro: Astronaut, day: int, inp: _Inputs) -> list[CardStatus]:
        return engine.evaluate_cards(self._ctx(astro, day, inp))

    # -- API-facing assessments -------------------------------------------------
    async def detail(self, astronaut_id: str, day: int | None = None) -> CrewDetail:
        astro = self.astronaut(astronaut_id)
        inp = await self._inputs(day)
        cards = self._cards(astro, inp.day, inp)
        records = self._records_upto(astro.id, inp.day, inp.overlays)
        series = mirror_gap.gap_series(records)
        return CrewDetail(
            astronaut=astro,
            day=inp.day,
            overall=engine.overall_level(cards),
            cards=cards,
            alerts=engine.flagged_alerts(cards),
            records=records,
            mirror_gap_series=[GapPoint(day=r.day, gap=g) for r, g in zip(records, series, strict=True)],
            radiation_source=inp.weather.source,
        )

    async def summaries(self, day: int | None = None) -> list[AstronautSummary]:
        inp = await self._inputs(day)
        out = []
        for astro in self._roster.values():
            cards = self._cards(astro, inp.day, inp)
            out.append(
                AstronautSummary(
                    astronaut=astro,
                    day=inp.day,
                    overall=engine.overall_level(cards),
                    cards={c.hazard: c.level for c in cards},
                )
            )
        return out

    async def alerts(self, day: int | None = None) -> list[CrewAlert]:
        return self._crew_alerts(await self._inputs(day))

    def _crew_alerts(self, inp: _Inputs) -> list[CrewAlert]:
        out: list[CrewAlert] = []
        for astro in self._roster.values():
            flagged = engine.flagged_alerts(self._cards(astro, inp.day, inp))
            out += [
                CrewAlert(**a.model_dump(), astronaut_id=astro.id, astronaut_name=astro.name, day=inp.day)
                for a in flagged
            ]
        return sorted(out, key=lambda a: (-a.level.rank, a.astronaut_id))

    async def distance_series(self) -> DistanceResponse:
        """Earth distance and signal delay at the end of every mission day (for the D panel chart)."""
        settings = await self._settings.get()
        data = await self._distance.get(settings.mission, settings.deep_space_mode)
        points = []
        for day in range(1, self.timeline.days + 1):
            sample = data.at(self.timeline.day_end(day))
            if sample is not None:
                points.append(
                    DistancePoint(
                        day=day,
                        distance_km=round(sample.distance_km, 1),
                        light_time_s=round(sample.light_time_s, 3),
                    )
                )
        return DistanceResponse(
            mission=settings.mission,
            target_name=data.target_name,
            source=data.source,
            data_as_of=data.data_as_of,
            reason=data.reason,
            days=points,
        )

    async def dashboard(self, day: int | None = None) -> DashboardResponse:
        """Everything the main dashboard needs, in one request."""
        inp = await self._inputs(day)
        crew = []
        for astro in self._roster.values():
            cards = self._cards(astro, inp.day, inp)
            crew.append(
                DashboardCrew(
                    astronaut=astro,
                    overall=engine.overall_level(cards),
                    cards=cards,
                    alerts=engine.flagged_alerts(cards),
                )
            )
        now = self.timeline.day_end(inp.day)
        since = now - timedelta(hours=t.EVENT_LOOKBACK_HOURS)
        recent = [
            MissionEvent(**e.model_dump(), mission_day=self.timeline.day_of(e.time))
            for e in inp.weather.events
            if e.kind in HAZARD_EVENT_KINDS and since < e.time <= now
        ]
        return DashboardResponse(
            disclaimer=DISCLAIMER,
            day=inp.day,
            mission_days=self.timeline.days,
            settings=MissionSettingsResponse.build(inp.settings, self.timeline.days),
            space_weather=SpaceWeatherStatus(
                source=inp.weather.source,
                data_as_of=inp.weather.data_as_of,
                reason=inp.weather.reason,
                events_last_24h=recent,
            ),
            distance=DistanceStatus(
                source=inp.distance.source,
                data_as_of=inp.distance.data_as_of,
                reason=inp.distance.reason,
                target_name=inp.distance.target_name,
            ),
            crew=crew,
            alerts=self._crew_alerts(inp),
        )


def sep_mission_days(
    events: list[SpaceWeatherEvent] | tuple[SpaceWeatherEvent, ...], timeline: MissionTimeline
) -> list[int]:
    """Sorted mission days that contain a real DONKI SEP event."""
    return sorted({timeline.day_of(e.time) for e in events if e.kind == EventKind.SEP})

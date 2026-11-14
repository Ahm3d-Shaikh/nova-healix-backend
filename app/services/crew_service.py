"""Assembles crew records, space weather and rules into assessments."""

from datetime import timedelta

from app.core.timeline import MissionTimeline
from app.models.alert import CrewAlert
from app.models.crew import (
    Astronaut, AstronautSummary, AstronautTimeline, CardStatus, CrewDetail, DailyRecord,
    DashboardCrew, DayLevels, GapPoint, TimelineResponse,
)
from app.models.dashboard import DashboardResponse, SpaceWeatherStatus
from app.models.enums import EventKind, Level
from app.models.settings import MissionSettings, MissionSettingsResponse
from app.models.space_weather import MissionEvent, SpaceWeatherData
from app.rules import engine, mirror_gap
from app.rules.context import RuleContext
from app.services.settings_service import SettingsService
from app.services.space_weather_service import SpaceWeatherService

HAZARD_EVENT_KINDS = (EventKind.SEP, EventKind.FLARE, EventKind.CME, EventKind.GEOSTORM)


class UnknownAstronaut(KeyError):
    pass


class CrewService:
    def __init__(
        self,
        roster: list[Astronaut],
        records: dict[str, list[DailyRecord]],
        timeline: MissionTimeline,
        weather: SpaceWeatherService,
        settings: SettingsService,
    ):
        self._roster = {a.id: a for a in roster}
        self._records = records
        self.timeline = timeline
        self._weather = weather
        self._settings = settings

    # -- lookups ---------------------------------------------------------------
    def astronaut(self, astronaut_id: str) -> Astronaut:
        try:
            return self._roster[astronaut_id.upper()]
        except KeyError:
            raise UnknownAstronaut(astronaut_id) from None

    def records(self, astronaut_id: str) -> list[DailyRecord]:
        return self._records[self.astronaut(astronaut_id).id]

    def resolve_day(self, day: int | None) -> int:
        return self.timeline.clamp(day if day is not None else self._settings.get().current_day)

    # -- core assessment (pure, no I/O) -----------------------------------------
    def _cards(
        self, astro: Astronaut, day: int, weather: SpaceWeatherData, settings: MissionSettings
    ) -> list[CardStatus]:
        ctx = RuleContext(
            day=day, now=self.timeline.day_end(day), records=self._records[astro.id][:day],
            events=weather.events, weather_source=weather.source, weather_as_of=weather.data_as_of,
            deep_space_mode=settings.deep_space_mode, mission=settings.mission,
        )
        return engine.evaluate_cards(ctx)

    async def _context(self, day: int | None):
        return self.resolve_day(day), await self._weather.get(self._settings.get().deep_space_mode), \
            self._settings.get()

    # -- API-facing assessments -------------------------------------------------
    async def detail(self, astronaut_id: str, day: int | None = None) -> CrewDetail:
        astro = self.astronaut(astronaut_id)
        day, weather, settings = await self._context(day)
        cards = self._cards(astro, day, weather, settings)
        records = self._records[astro.id][:day]
        series = mirror_gap.gap_series(records)
        return CrewDetail(
            astronaut=astro, day=day, overall=engine.overall_level(cards), cards=cards,
            alerts=engine.flagged_alerts(cards), records=records,
            mirror_gap_series=[GapPoint(day=r.day, gap=g) for r, g in zip(records, series)],
            radiation_source=weather.source,
        )

    async def summaries(self, day: int | None = None) -> list[AstronautSummary]:
        day, weather, settings = await self._context(day)
        out = []
        for astro in self._roster.values():
            cards = self._cards(astro, day, weather, settings)
            out.append(AstronautSummary(
                astronaut=astro, day=day, overall=engine.overall_level(cards),
                cards={c.hazard: c.level for c in cards},
            ))
        return out

    async def alerts(self, day: int | None = None) -> list[CrewAlert]:
        day, weather, settings = await self._context(day)
        return self._crew_alerts(day, weather, settings)

    def _crew_alerts(self, day, weather, settings) -> list[CrewAlert]:
        out: list[CrewAlert] = []
        for astro in self._roster.values():
            flagged = engine.flagged_alerts(self._cards(astro, day, weather, settings))
            out += [CrewAlert(**a.model_dump(), astronaut_id=astro.id, astronaut_name=astro.name, day=day)
                    for a in flagged]
        return sorted(out, key=lambda a: (-a.level.rank, a.astronaut_id))

    async def timeline_all(self, astronaut_id: str | None = None) -> TimelineResponse:
        """Card levels for every mission day, so the day slider needs one request."""
        _, weather, settings = await self._context(None)
        roster = [self.astronaut(astronaut_id)] if astronaut_id else list(self._roster.values())
        crew = []
        for astro in roster:
            days = []
            for day in range(1, self.timeline.days + 1):
                cards = self._cards(astro, day, weather, settings)
                days.append(DayLevels(day=day, overall=engine.overall_level(cards),
                                      cards={c.hazard: c.level for c in cards}))
            crew.append(AstronautTimeline(astronaut_id=astro.id, days=days))
        storm_days = sorted({self.timeline.day_of(e.time) for e in weather.events if e.kind == EventKind.SEP})
        return TimelineResponse(mission_days=self.timeline.days, storm_days=storm_days,
                                radiation_source=weather.source, crew=crew)

    async def dashboard(self, day: int | None = None) -> DashboardResponse:
        """Everything the main dashboard needs, in one request."""
        day, weather, settings = await self._context(day)
        crew = []
        for astro in self._roster.values():
            cards = self._cards(astro, day, weather, settings)
            crew.append(DashboardCrew(astronaut=astro, overall=engine.overall_level(cards), cards=cards,
                                      alerts=engine.flagged_alerts(cards)))
        now = self.timeline.day_end(day)
        recent = [
            MissionEvent(**e.model_dump(), mission_day=self.timeline.day_of(e.time))
            for e in weather.events
            if e.kind in HAZARD_EVENT_KINDS and now - timedelta(hours=24) < e.time <= now
        ]
        return DashboardResponse(
            day=day, mission_days=self.timeline.days,
            settings=MissionSettingsResponse.build(settings, self.timeline.days),
            space_weather=SpaceWeatherStatus(source=weather.source, data_as_of=weather.data_as_of,
                                             reason=weather.reason, events_last_24h=recent),
            crew=crew, alerts=self._crew_alerts(day, weather, settings),
        )


def sep_mission_days(events, timeline: MissionTimeline) -> set[int]:
    return {timeline.day_of(e.time) for e in events if e.kind == EventKind.SEP}

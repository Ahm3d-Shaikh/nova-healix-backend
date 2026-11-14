"""Assembles crew records, space weather and rules into assessments."""

from datetime import timedelta

from app.core.errors import UnknownAstronautError
from app.core.timeline import MissionTimeline
from app.models.alert import CrewAlert
from app.models.crew import (
    Astronaut,
    AstronautSummary,
    AstronautTimeline,
    CardStatus,
    CrewDetail,
    DailyRecord,
    DashboardCrew,
    DayLevels,
    GapPoint,
    TimelineResponse,
)
from app.models.dashboard import DashboardResponse, SpaceWeatherStatus
from app.models.enums import EventKind, worst
from app.models.settings import MissionSettings, MissionSettingsResponse
from app.models.space_weather import MissionEvent, SpaceWeatherData, SpaceWeatherEvent
from app.rules import engine, mirror_gap
from app.rules import thresholds as t
from app.rules.context import RuleContext
from app.services.settings_service import SettingsService
from app.services.space_weather_service import SpaceWeatherService

TIMELINE_CACHE_SIZE = 16
HAZARD_EVENT_KINDS = (EventKind.SEP, EventKind.FLARE, EventKind.CME, EventKind.GEOSTORM)


class CrewService:
    def __init__(
        self,
        roster: list[Astronaut],
        records: dict[str, list[DailyRecord]],
        timeline: MissionTimeline,
        weather: SpaceWeatherService,
        settings: SettingsService,
    ) -> None:
        self._roster = {a.id: a for a in roster}
        self._records = records
        self.timeline = timeline
        self._weather = weather
        self._settings = settings
        self._timeline_cache: dict[tuple[object, ...], TimelineResponse] = {}

    # -- lookups ---------------------------------------------------------------
    def astronaut(self, astronaut_id: str) -> Astronaut:
        try:
            return self._roster[astronaut_id.upper()]
        except KeyError:
            raise UnknownAstronautError(astronaut_id) from None

    def records(self, astronaut_id: str) -> list[DailyRecord]:
        return self._records[self.astronaut(astronaut_id).id]

    def resolve_day(self, day: int | None) -> int:
        """Explicit day, else the saved 'current day'. Raises InvalidDayError when out of range."""
        return self.timeline.validate(self._settings.get().current_day if day is None else day)

    # -- core assessment (pure, no I/O) -----------------------------------------
    def _ctx(self, astro: Astronaut, day: int, weather: SpaceWeatherData, settings: MissionSettings) -> RuleContext:
        return RuleContext(
            day=day,
            now=self.timeline.day_end(day),
            records=self._records[astro.id][:day],
            events=weather.events,
            weather_source=weather.source,
            weather_as_of=weather.data_as_of,
            deep_space_mode=settings.deep_space_mode,
            mission=settings.mission,
        )

    def _cards(
        self, astro: Astronaut, day: int, weather: SpaceWeatherData, settings: MissionSettings
    ) -> list[CardStatus]:
        return engine.evaluate_cards(self._ctx(astro, day, weather, settings))

    async def _context(self, day: int | None) -> tuple[int, SpaceWeatherData, MissionSettings]:
        resolved = self.resolve_day(day)
        settings = self._settings.get()
        return resolved, await self._weather.get(settings.deep_space_mode), settings

    # -- API-facing assessments -------------------------------------------------
    async def detail(self, astronaut_id: str, day: int | None = None) -> CrewDetail:
        astro = self.astronaut(astronaut_id)
        day, weather, settings = await self._context(day)
        cards = self._cards(astro, day, weather, settings)
        records = self._records[astro.id][:day]
        series = mirror_gap.gap_series(records)
        return CrewDetail(
            astronaut=astro,
            day=day,
            overall=engine.overall_level(cards),
            cards=cards,
            alerts=engine.flagged_alerts(cards),
            records=records,
            mirror_gap_series=[GapPoint(day=r.day, gap=g) for r, g in zip(records, series, strict=True)],
            radiation_source=weather.source,
        )

    async def summaries(self, day: int | None = None) -> list[AstronautSummary]:
        day, weather, settings = await self._context(day)
        out = []
        for astro in self._roster.values():
            cards = self._cards(astro, day, weather, settings)
            out.append(
                AstronautSummary(
                    astronaut=astro,
                    day=day,
                    overall=engine.overall_level(cards),
                    cards={c.hazard: c.level for c in cards},
                )
            )
        return out

    async def alerts(self, day: int | None = None) -> list[CrewAlert]:
        day, weather, settings = await self._context(day)
        return self._crew_alerts(day, weather, settings)

    def _crew_alerts(self, day: int, weather: SpaceWeatherData, settings: MissionSettings) -> list[CrewAlert]:
        out: list[CrewAlert] = []
        for astro in self._roster.values():
            flagged = engine.flagged_alerts(self._cards(astro, day, weather, settings))
            out += [
                CrewAlert(**a.model_dump(), astronaut_id=astro.id, astronaut_name=astro.name, day=day) for a in flagged
            ]
        return sorted(out, key=lambda a: (-a.level.rank, a.astronaut_id))

    async def timeline_all(self, astronaut_id: str | None = None) -> TimelineResponse:
        """Card levels for every mission day, so the day slider needs one request.

        Only levels are computed (no metrics) and results are cached per data snapshot,
        because the answer depends only on weather data, mission and deep-space mode.
        """
        _, weather, settings = await self._context(None)
        astro_id = self.astronaut(astronaut_id).id if astronaut_id else None
        key = (weather.source, weather.data_as_of, settings.mission, settings.deep_space_mode, astro_id)
        cached = self._timeline_cache.get(key)
        if cached is None:
            roster = [self._roster[astro_id]] if astro_id else list(self._roster.values())
            cached = TimelineResponse(
                mission_days=self.timeline.days,
                storm_days=sep_mission_days(weather.events, self.timeline),
                radiation_source=weather.source,
                crew=[self._astronaut_timeline(a, weather, settings) for a in roster],
            )
            if len(self._timeline_cache) >= TIMELINE_CACHE_SIZE:
                self._timeline_cache.pop(next(iter(self._timeline_cache)))
            self._timeline_cache[key] = cached
        return cached

    def _astronaut_timeline(
        self, astro: Astronaut, weather: SpaceWeatherData, settings: MissionSettings
    ) -> AstronautTimeline:
        days = []
        for day in range(1, self.timeline.days + 1):
            levels = engine.evaluate_levels(self._ctx(astro, day, weather, settings))
            days.append(DayLevels(day=day, overall=worst(list(levels.values())), cards=levels))
        return AstronautTimeline(astronaut_id=astro.id, days=days)

    async def dashboard(self, day: int | None = None) -> DashboardResponse:
        """Everything the main dashboard needs, in one request."""
        day, weather, settings = await self._context(day)
        crew = []
        for astro in self._roster.values():
            cards = self._cards(astro, day, weather, settings)
            crew.append(
                DashboardCrew(
                    astronaut=astro,
                    overall=engine.overall_level(cards),
                    cards=cards,
                    alerts=engine.flagged_alerts(cards),
                )
            )
        now = self.timeline.day_end(day)
        since = now - timedelta(hours=t.EVENT_LOOKBACK_HOURS)
        recent = [
            MissionEvent(**e.model_dump(), mission_day=self.timeline.day_of(e.time))
            for e in weather.events
            if e.kind in HAZARD_EVENT_KINDS and since < e.time <= now
        ]
        return DashboardResponse(
            day=day,
            mission_days=self.timeline.days,
            settings=MissionSettingsResponse.build(settings, self.timeline.days),
            space_weather=SpaceWeatherStatus(
                source=weather.source,
                data_as_of=weather.data_as_of,
                reason=weather.reason,
                events_last_24h=recent,
            ),
            crew=crew,
            alerts=self._crew_alerts(day, weather, settings),
        )


def sep_mission_days(
    events: list[SpaceWeatherEvent] | tuple[SpaceWeatherEvent, ...], timeline: MissionTimeline
) -> list[int]:
    """Sorted mission days that contain a real DONKI SEP event."""
    return sorted({timeline.day_of(e.time) for e in events if e.kind == EventKind.SEP})

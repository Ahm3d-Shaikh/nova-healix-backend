"""Assembles crew records, space weather and rules into assessments."""

from app.core.timeline import MissionTimeline
from app.models.alert import CrewAlert
from app.models.crew import (
    Astronaut, AstronautSummary, CrewDetail, DailyRecord, GapPoint,
)
from app.models.enums import EventKind, Hazard, RIDGE_HAZARDS
from app.rules import engine, mirror_gap
from app.rules.context import RuleContext
from app.services.settings_service import SettingsService
from app.services.space_weather_service import SpaceWeatherService


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

    # -- assessments -----------------------------------------------------------
    async def detail(self, astronaut_id: str, day: int | None = None) -> CrewDetail:
        astro = self.astronaut(astronaut_id)
        day = self.resolve_day(day)
        records = self._records[astro.id][:day]
        weather = await self._weather.get(self._settings.get().deep_space_mode)
        settings = self._settings.get()
        ctx = RuleContext(
            day=day, now=self.timeline.day_end(day), records=records, events=weather.events,
            weather_source=weather.source, weather_as_of=weather.data_as_of,
            deep_space_mode=settings.deep_space_mode, mission=settings.mission,
        )
        cards = engine.evaluate_cards(ctx)
        series = mirror_gap.gap_series(records)
        return CrewDetail(
            astronaut=astro, day=day, overall=engine.overall_level(cards), cards=cards,
            alerts=engine.flagged_alerts(cards), records=records,
            mirror_gap_series=[GapPoint(day=r.day, gap=g) for r, g in zip(records, series)],
            radiation_source=weather.source,
        )

    async def summaries(self, day: int | None = None) -> list[AstronautSummary]:
        out = []
        for astro in self._roster.values():
            d = await self.detail(astro.id, day)
            out.append(AstronautSummary(
                astronaut=astro, day=d.day, overall=d.overall,
                cards={c.hazard: c.level for c in d.cards if c.hazard in (*RIDGE_HAZARDS, Hazard.MIRROR)},
            ))
        return out

    async def alerts(self, day: int | None = None) -> list[CrewAlert]:
        out: list[CrewAlert] = []
        for astro in self._roster.values():
            d = await self.detail(astro.id, day)
            out += [CrewAlert(**a.model_dump(), astronaut_id=astro.id, astronaut_name=astro.name, day=d.day)
                    for a in d.alerts]
        return sorted(out, key=lambda a: (-a.level.rank, a.astronaut_id))


def sep_mission_days(events, timeline: MissionTimeline) -> set[int]:
    return {timeline.day_of(e.time) for e in events if e.kind == EventKind.SEP}

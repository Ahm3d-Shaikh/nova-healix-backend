"""Wires services together. Built once at startup; tests can build their own."""

from dataclasses import dataclass

from app.core.config import Settings
from app.core.timeline import MissionTimeline
from app.services.crew_generator import ASTRONAUTS, generate_crew
from app.services.crew_service import CrewService, sep_mission_days
from app.services.donki_client import DonkiClient
from app.services.isolation_service import IsolationService
from app.services.mirror_gap_service import MirrorGapService
from app.services.settings_service import SettingsService
from app.services.space_weather_service import SpaceWeatherService


@dataclass
class Container:
    settings: Settings
    timeline: MissionTimeline
    weather: SpaceWeatherService
    mission_settings: SettingsService
    crew: CrewService
    mirror_gap: MirrorGapService
    isolation: IsolationService


def build_container(settings: Settings, donki: DonkiClient) -> Container:
    timeline = MissionTimeline(start=settings.mission_start, days=settings.mission_days)
    weather = SpaceWeatherService(
        donki, settings.storm_window_start, settings.storm_window_end,
        settings.donki_snapshot_path, settings.donki_cache_ttl_seconds,
    )
    # Simulated dose spikes follow the bundled (real) snapshot so crew data stays
    # deterministic even when live DONKI data changes.
    sep_days = sep_mission_days(weather.load_snapshot().events, timeline)
    records = generate_crew(settings.crew_seed, settings.mission_days, sep_days)

    mission_settings = SettingsService(settings.mission_days)
    crew = CrewService(ASTRONAUTS, records, timeline, weather, mission_settings)
    return Container(settings, timeline, weather, mission_settings, crew, MirrorGapService(crew), IsolationService(crew))

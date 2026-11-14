"""Wires services together. Built once at startup; tests can build their own."""

import logging
from dataclasses import dataclass

from app.core.config import Settings
from app.core.timeline import MissionTimeline
from app.db.base import Database, DatabaseError
from app.models.crew import Astronaut, DailyRecord
from app.repositories.cache import CacheRepository
from app.repositories.crew import CrewRepository
from app.repositories.isolation import IsolationRepository
from app.repositories.settings import SettingsRepository
from app.services.companion import Companion
from app.services.crew_generator import ASTRONAUTS, generate_crew
from app.services.crew_service import CrewService, sep_mission_days
from app.services.distance_service import DistanceService
from app.services.donki_client import DonkiClient
from app.services.horizons_client import HorizonsClient
from app.services.isolation_service import IsolationService
from app.services.settings_service import SettingsService
from app.services.space_weather_service import SpaceWeatherService

log = logging.getLogger(__name__)


@dataclass
class Container:
    settings: Settings
    timeline: MissionTimeline
    weather: SpaceWeatherService
    distance: DistanceService
    mission_settings: SettingsService
    crew: CrewService
    isolation: IsolationService
    database: str  # "supabase" | "memory"
    ai_checkin_enabled: bool


async def build_container(
    settings: Settings,
    donki: DonkiClient,
    horizons: HorizonsClient,
    db: Database,
    companion: Companion | None = None,
) -> Container:
    timeline = MissionTimeline(start=settings.mission_start, days=settings.mission_days)
    cache = CacheRepository(db)
    weather = SpaceWeatherService(
        donki,
        settings.storm_window_start,
        settings.storm_window_end,
        settings.donki_snapshot_path,
        cache=cache,
        cache_ttl_seconds=settings.donki_cache_ttl_seconds,
        fetch_timeout_seconds=settings.donki_total_timeout_seconds,
    )
    window_start, window_end = settings.mission_window
    distance = DistanceService(
        horizons,
        window_start,
        window_end,
        settings.horizons_snapshot_path,
        cache,
        cache_ttl_seconds=settings.horizons_cache_ttl_seconds,
    )
    # Simulated dose spikes follow the bundled (real) snapshot so crew data stays
    # deterministic even when live DONKI data changes.
    sep_days = set(sep_mission_days(weather.load_snapshot().events, timeline))
    generated = generate_crew(settings.crew_seed, settings.mission_days, sep_days)
    roster, records = await load_crew(CrewRepository(db), generated, settings)

    mission_settings = SettingsService(settings.mission_days, SettingsRepository(db))
    isolation_repo = IsolationRepository(db)
    crew = CrewService(
        roster,
        records,
        timeline,
        weather=weather,
        settings=mission_settings,
        distance=distance,
        isolation=isolation_repo,
    )
    return Container(
        settings=settings,
        timeline=timeline,
        weather=weather,
        distance=distance,
        mission_settings=mission_settings,
        crew=crew,
        isolation=IsolationService(crew, isolation_repo, companion),
        database=db.name,
        ai_checkin_enabled=companion is not None,
    )


async def load_crew(
    repo: CrewRepository, generated: dict[str, list[DailyRecord]], settings: Settings
) -> tuple[list[Astronaut], dict[str, list[DailyRecord]]]:
    """Crew roster and daily records from the database, seeding an empty database first.

    Falls back to the generated (simulated) crew if the database is unreachable, so the
    dashboard keeps working; check-ins and settings will still need the database.
    """
    try:
        roster = await repo.astronauts()
        if not roster and settings.seed_simulated_crew:
            await repo.seed(ASTRONAUTS, generated)
            log.info("Seeded %d simulated astronauts into the database", len(ASTRONAUTS))
            return list(ASTRONAUTS), generated
        records = await repo.records()
    except DatabaseError as exc:
        log.error("Could not load crew from the database (%s); using the simulated crew", exc)
        return list(ASTRONAUTS), generated

    complete: dict[str, list[DailyRecord]] = {}
    kept: list[Astronaut] = []
    for astro in roster:
        recs = records.get(astro.id, [])
        if [r.day for r in recs] == list(range(1, settings.mission_days + 1)):
            complete[astro.id] = recs
            kept.append(astro)
        elif astro.id in generated:
            log.warning("Astronaut %s has incomplete records in the database; using simulated data", astro.id)
            complete[astro.id] = generated[astro.id]
            kept.append(astro)
        else:
            log.warning("Skipping astronaut %s: no daily records for all %d days", astro.id, settings.mission_days)
    return kept, complete

"""Wires the services together. Built once at startup; tests build their own."""

import logging
import time
from dataclasses import dataclass

from app.core.config import Settings
from app.db.base import Database, DatabaseError
from app.domain.mission_plan import (
    CAREER_DOSE_LIMIT_MSV,
    FLIGHT_DIRECTOR,
    FLIGHT_SURGEON,
    GENERATED_HOURS,
    MISSION_DURATION_DAYS,
)
from app.domain.store import MissionData
from app.nasa.donki_client import DonkiClient
from app.nasa.horizons_client import HorizonsClient
from app.nasa.service import NasaDataService
from app.nasa.space_weather_service import SpaceWeatherService
from app.repositories.cache import CacheRepository
from app.repositories.echo import EchoRepository
from app.repositories.state import StateRepository
from app.schemas.mission import MissionConfig, Team
from app.services.actions import ActionsService
from app.services.analysis import AnalysisService
from app.services.clock import MissionClock, Trajectory
from app.services.companion import CompanionService, GeminiReplier, Replier
from app.services.crew_mode import CrewModeService
from app.services.echo import EchoService
from app.services.echo_companion import EchoCompanion, GeminiEchoCompanion
from app.services.gemini import GeminiClient
from app.services.mobility import MobilityService
from app.services.overview import OverviewService
from app.services.telemetry import TelemetryService

log = logging.getLogger(__name__)


@dataclass
class Container:
    settings: Settings
    clock: MissionClock
    trajectory: Trajectory
    data: MissionData
    state: StateRepository
    telemetry: TelemetryService
    analysis: AnalysisService
    crew_mode: CrewModeService
    companion: CompanionService  # Nova, the private companion
    echo: EchoService  # ECHO, the scored isolation check-in chat
    actions: ActionsService
    mobility: MobilityService
    overview: OverviewService
    nasa: NasaDataService | None  # None when no NASA clients were given (offline tests)
    database: str  # "supabase" | "memory"

    def mission_config(self) -> MissionConfig:
        return MissionConfig(
            code="NHX-1",
            name="Mars Transit",
            vehicle="DSV Meridian",
            duration_days=MISSION_DURATION_DAYS,
            launch_epoch_ms=self.clock.launch_epoch_ms,
            career_dose_limit_msv=CAREER_DOSE_LIMIT_MSV,
            current_day=self.clock.current_day(),
            trajectory_au=self.trajectory.au,
            trajectory_source=self.trajectory.source,
            team=Team(flight_surgeon=FLIGHT_SURGEON, flight_director=FLIGHT_DIRECTOR),
        )


async def resolve_launch_epoch(settings: Settings, repo: StateRepository, now_ms: float) -> int:
    """Settings win; else the saved epoch while 'now' is still inside the generated data; else a fresh anchor."""
    if settings.launch_epoch_ms is not None:
        return settings.launch_epoch_ms
    saved: int | None = None
    try:
        saved = await repo.launch_epoch_ms()
    except DatabaseError as exc:
        log.error("Could not read the saved launch epoch (%s)", exc)
    if saved is not None:
        hour = (now_ms - saved) / 3_600_000
        if 0 <= hour < GENERATED_HOURS - 12:
            return saved
        log.warning("Saved launch epoch is outside the generated data window; re-anchoring to mission day 142")
    fresh = MissionClock.default_launch_epoch_ms(now_ms)
    try:
        await repo.save_launch_epoch_ms(fresh)
    except DatabaseError as exc:
        log.error("Could not save the launch epoch (%s)", exc)
    return fresh


async def build_container(
    settings: Settings,
    db: Database,
    *,
    donki: DonkiClient | None = None,
    horizons: HorizonsClient | None = None,
    gemini: GeminiClient | None = None,
    replier: Replier | None = None,
    echo_companion: EchoCompanion | None = None,
    now_ms: float | None = None,
    trajectory: Trajectory | None = None,
) -> Container:
    now = now_ms if now_ms is not None else time.time() * 1000
    repo = StateRepository(db)
    echo_repo = EchoRepository(db)
    clock = MissionClock(await resolve_launch_epoch(settings, repo, now), (lambda: now) if now_ms is not None else None)
    data = MissionData()
    await repo.load_into(data)
    try:
        await echo_repo.load_into(data)
    except DatabaseError as exc:
        log.error("Could not load saved ECHO check-ins (%s)", exc)
    traj = trajectory or Trajectory()
    if len(traj.au) < MISSION_DURATION_DAYS + 1:
        raise ValueError(f"trajectory needs at least {MISSION_DURATION_DAYS + 1} values")

    if gemini is not None:
        replier = replier or GeminiReplier(gemini, settings.gemini_chat_model)
        echo_companion = echo_companion or GeminiEchoCompanion(
            gemini, settings.gemini_model, settings.gemini_chat_model, settings.gemini_chat_timeout_seconds
        )
    nasa = None
    if donki is not None and horizons is not None:
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
        nasa = NasaDataService(weather=weather, horizons=horizons, cache=cache, data=data, trajectory=traj, clock=clock)

    analysis = AnalysisService(data, clock, traj)
    return Container(
        settings=settings,
        clock=clock,
        trajectory=traj,
        data=data,
        state=repo,
        telemetry=TelemetryService(data, clock),
        analysis=analysis,
        crew_mode=CrewModeService(data, clock, repo),
        companion=CompanionService(
            data, clock, traj, repo, FLIGHT_SURGEON, replier=replier, enabled=settings.companion_enabled
        ),
        echo=EchoService(data, clock, echo_repo, echo_companion),
        actions=ActionsService(data, clock, traj, repo, FLIGHT_SURGEON),
        mobility=MobilityService(data, clock, repo),
        overview=OverviewService(data, clock, traj, analysis),
        nasa=nasa,
        database=db.name,
    )

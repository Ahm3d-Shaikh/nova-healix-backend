"""Real NASA data feeding the simulated mission.

* NASA DONKI: a real storm episode (May 2024) is replayed on mission day 97, as extra mission events.
  The first solar energetic particle (SEP) event lands on the mission's own solar particle event
  (`spe-97`), so the real sequence of flares and particle events runs around it.
* NASA JPL Horizons: the real Earth-Mars distance on the arrival date sets the far end of the
  Earth-ship distance curve (`MissionConfig.trajectoryAu`); the signal delay is derived from it.

Both fall back silently (live -> cached -> bundled snapshot / smooth model curve) so the API never waits
on NASA. Mission events from NASA carry `source: "NASA DONKI"`.
"""

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta

from app.domain.mission_plan import MISSION_DURATION_DAYS, at
from app.domain.store import MissionData
from app.nasa.horizons_client import HorizonsClient, HorizonsError
from app.nasa.models import EventKind, SpaceWeatherEvent
from app.nasa.space_weather_service import SpaceWeatherService
from app.repositories.cache import CacheRepository
from app.schemas.mission import MissionEvent
from app.services.clock import MissionClock, Trajectory

log = logging.getLogger(__name__)

KM_PER_AU = 149_597_870.7
SOURCE_DONKI = "NASA DONKI"
SOURCE_HORIZONS = "NASA JPL Horizons"
MARS = "499"
SPE_START_HOUR = at(97, 3)  # start of the mission's own solar particle event (`spe-97`)


def _trajectory_curve(arrival_au: float) -> list[float]:
    """Earth-ship distance per day: ~0 at launch growing smoothly to `arrival_au` at arrival."""
    return [
        0.004 + (arrival_au - 0.004) * min(1.0, (i + 1) / MISSION_DURATION_DAYS) ** 1.3
        for i in range(MISSION_DURATION_DAYS + 1)
    ]


def map_events(events: list[SpaceWeatherEvent], spe_start_hour: float = SPE_START_HOUR) -> list[MissionEvent]:
    """Real storm events as mission events, aligned so the first SEP starts at `spe_start_hour`.

    Kept: every SEP, X-class flares and strong geomagnetic storms (Kp 7+). Everything else is noise here.
    """
    seps = sorted(e.time for e in events if e.kind == EventKind.SEP)
    if not seps:
        return []
    anchor = seps[0]
    out: list[MissionEvent] = []
    for e in sorted(events, key=lambda x: x.time):
        start = spe_start_hour + (e.time - anchor).total_seconds() / 3600
        if e.kind == EventKind.SEP:
            kind, label, hazards = "spe", "Solar energetic particle event (NASA DONKI)", ["radiation"]
        elif e.kind == EventKind.FLARE and (e.class_type or "").upper().startswith("X"):
            kind, label, hazards = "anomaly", f"{e.class_type} solar flare (NASA DONKI)", ["radiation"]
        elif e.kind == EventKind.GEOSTORM and (e.kp_index or 0) >= 7:
            kind, label, hazards = "anomaly", f"Geomagnetic storm, Kp {e.kp_index:g} (NASA DONKI)", ["distance"]
        else:
            continue
        out.append(
            MissionEvent(
                id=f"donki-{e.id}",
                kind=kind,
                label=label,
                start=round(start, 3),
                end=round(start + 1, 3),
                crew_ids=[],
                hazards=hazards,
                source=SOURCE_DONKI,
            )
        )
    return out


class NasaDataService:
    def __init__(
        self,
        *,
        weather: SpaceWeatherService,
        horizons: HorizonsClient,
        cache: CacheRepository,
        data: MissionData,
        trajectory: Trajectory,
        clock: MissionClock,
    ) -> None:
        self._weather = weather
        self._horizons = horizons
        self._cache = cache
        self._data = data
        self._trajectory = trajectory
        self._clock = clock

    async def refresh(self) -> None:
        """Pull both feeds. Never raises: the simulation keeps working on its own defaults."""
        await asyncio.gather(self._refresh_storm(), self._refresh_trajectory(), return_exceptions=True)

    async def _refresh_storm(self) -> None:
        try:
            result = await self._weather.get()
            events = map_events(result.events)
            self._data.set_external_events(events)
            log.info(
                "NASA DONKI: %d storm events mapped onto mission day 97 (source: %s)", len(events), result.source.value
            )
        except Exception:
            log.exception("NASA DONKI refresh failed; the mission keeps its built-in events")

    async def _refresh_trajectory(self) -> None:
        launch = datetime.fromtimestamp(self._clock.launch_epoch_ms / 1000, UTC)
        arrival = (launch + timedelta(days=MISSION_DURATION_DAYS)).date()
        key = f"horizons:mars-arrival:{arrival.isoformat()}"
        found = await self._arrival_au(arrival, key)
        if found is None:
            return
        au, fetched_at = found
        self._trajectory.au = _trajectory_curve(au)
        self._trajectory.source = SOURCE_HORIZONS
        self._trajectory.as_of = fetched_at
        self._data.touch()  # delays changed: cached analyses are stale
        log.info(
            "NASA JPL Horizons: Earth-Mars distance %.3f AU on %s sets the arrival end of the trajectory", au, arrival
        )

    async def _arrival_au(self, arrival: date, key: str) -> tuple[float, datetime] | None:
        cached = await self._cache.get(key)
        if cached is not None:
            return float(cached[0]["au"]), cached[1]
        try:
            samples = await self._horizons.fetch_vectors(MARS, arrival, arrival + timedelta(days=1))
        except HorizonsError as exc:
            log.warning("NASA JPL Horizons unavailable (%s); using the model trajectory", exc)
            return None
        au = samples[0].distance_km / KM_PER_AU
        fetched_at = datetime.now(UTC)
        await self._cache.put(key, {"au": au}, fetched_at)
        return au, fetched_at


__all__ = ["NasaDataService", "map_events"]

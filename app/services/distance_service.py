"""Earth-to-crew distance from JPL Horizons, with fallback: live -> cache (memory, then DB) -> bundled snapshot.

The crew's location is modelled by the mission destination: the ISS itself, the Moon, or Mars.
Samples cover the simulated mission window, so mission day N uses the real geometry of that date.
"""

import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from app.models.distance import DistanceData, DistanceSample
from app.models.enums import DataSource, Mission
from app.repositories.cache import CacheRepository
from app.services.horizons_client import HorizonsClient, HorizonsError

log = logging.getLogger(__name__)

REASON_DEEP_SPACE = "deep_space_mode"
REASON_UNAVAILABLE = "live_unavailable"


@dataclass(frozen=True)
class Target:
    command: str  # Horizons COMMAND
    name: str


TARGETS: dict[Mission, Target] = {
    Mission.ISS: Target("-125544", "International Space Station"),
    Mission.MOON: Target("301", "Moon"),
    Mission.MARS: Target("499", "Mars"),
}


@dataclass
class _Entry:
    samples: list[DistanceSample]
    fetched_at: datetime
    stored_at: float


class DistanceService:
    def __init__(
        self,
        client: HorizonsClient,
        window_start: date,
        window_end: date,
        snapshot_path: Path,
        cache: CacheRepository,
        *,
        cache_ttl_seconds: int = 86400,
        retry_after_seconds: int = 120,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._start = window_start
        self._end = window_end
        self._snapshot_path = snapshot_path
        self._db_cache = cache
        self._ttl = cache_ttl_seconds
        self._retry_after = retry_after_seconds
        self._clock = clock
        self._now = now
        self._mem: dict[Mission, _Entry] = {}
        self._backoff_until: dict[Mission, float] = {}
        self._lock = asyncio.Lock()
        self._snapshot: dict[str, Any] | None = None

    def _key(self, mission: Mission) -> str:
        return f"horizons:{mission.value}:{self._start.isoformat()}:{self._end.isoformat()}"

    async def get(self, mission: Mission, deep_space_mode: bool = False) -> DistanceData:
        if deep_space_mode:
            return await self._fallback(mission, REASON_DEEP_SPACE)
        async with self._lock:
            entry = self._mem.get(mission)
            if entry and self._clock() - entry.stored_at < self._ttl:
                return self._data(mission, entry.samples, entry.fetched_at, DataSource.LIVE, None)
            if self._clock() < self._backoff_until.get(mission, 0.0):
                return await self._fallback(mission, REASON_UNAVAILABLE)
            try:
                samples = await self._client.fetch_vectors(TARGETS[mission].command, self._start, self._end)
            except HorizonsError as exc:
                log.warning("Live Horizons fetch for %s failed: %s", mission.value, exc)
                self._backoff_until[mission] = self._clock() + self._retry_after
                return await self._fallback(mission, REASON_UNAVAILABLE)
            fetched = self._now()
            self._mem[mission] = _Entry(samples, fetched, self._clock())
            await self._db_cache.put(self._key(mission), [s.model_dump(mode="json") for s in samples], fetched)
            return self._data(mission, samples, fetched, DataSource.LIVE, None)

    async def _fallback(self, mission: Mission, reason: str) -> DistanceData:
        entry = self._mem.get(mission)
        if entry:
            return self._data(mission, entry.samples, entry.fetched_at, DataSource.CACHED, reason)
        stored = await self._db_cache.get(self._key(mission))
        if stored is not None:
            payload, fetched = stored
            samples = [DistanceSample.model_validate(s) for s in payload]
            return self._data(mission, samples, fetched, DataSource.CACHED, reason)
        return self.load_snapshot(mission).model_copy(update={"reason": reason})

    def load_snapshot(self, mission: Mission) -> DistanceData:
        """Bundled Horizons tables (real responses saved by scripts/build_horizons_snapshot.py)."""
        if self._snapshot is None:
            self._snapshot = json.loads(self._snapshot_path.read_text())
        raw = self._snapshot["missions"][mission.value]
        return self._data(
            mission,
            [DistanceSample.model_validate(s) for s in raw["samples"]],
            datetime.fromisoformat(str(self._snapshot["fetched_at"])),
            DataSource.SNAPSHOT,
            None,
        )

    @staticmethod
    def _data(
        mission: Mission, samples: list[DistanceSample], as_of: datetime, source: DataSource, reason: str | None
    ) -> DistanceData:
        target = TARGETS[mission]
        return DistanceData(
            mission=mission,
            target=target.command,
            target_name=target.name,
            source=source,
            data_as_of=as_of,
            reason=reason,
            samples=samples,
        )

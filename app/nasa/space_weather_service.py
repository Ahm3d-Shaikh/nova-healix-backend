"""Space-weather data with fallback: live -> cache (memory, then database) -> snapshot file."""

import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from app.nasa.donki_client import DonkiClient, DonkiError, DonkiRateLimited
from app.nasa.models import DataSource, SpaceWeatherData, SpaceWeatherEvent
from app.repositories.cache import CacheRepository

log = logging.getLogger(__name__)

REASON_DEEP_SPACE = "deep_space_mode"
REASON_UNAVAILABLE = "live_unavailable"
REASON_RATE_LIMITED = "rate_limited"


@dataclass
class _CacheEntry:
    events: list[SpaceWeatherEvent]
    fetched_at: datetime
    stored_at: float  # monotonic seconds


class SpaceWeatherService:
    def __init__(
        self,
        client: DonkiClient,
        window_start: date,
        window_end: date,
        snapshot_path: Path,
        *,
        cache: CacheRepository | None = None,
        cache_ttl_seconds: int = 3600,
        retry_after_seconds: int = 60,
        fetch_timeout_seconds: float = 12.0,
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
        self._fetch_timeout = fetch_timeout_seconds
        self._clock = clock
        self._now = now
        self._cache: _CacheEntry | None = None
        self._lock = asyncio.Lock()
        self._snapshot: SpaceWeatherData | None = None
        self._backoff_until = 0.0  # monotonic time before which we do not call DONKI
        self._backoff_reason = REASON_UNAVAILABLE

    @property
    def window(self) -> tuple[date, date]:
        return self._start, self._end

    def load_snapshot(self) -> SpaceWeatherData:
        """The bundled DONKI snapshot (a real response saved to disk)."""
        if self._snapshot is None:
            raw = json.loads(self._snapshot_path.read_text())
            self._snapshot = SpaceWeatherData(
                source=DataSource.SNAPSHOT,
                data_as_of=datetime.fromisoformat(raw["fetched_at"]),
                reason=None,
                events=[SpaceWeatherEvent.model_validate(e) for e in raw["events"]],
            )
        return self._snapshot

    async def get(self, deep_space_mode: bool = False) -> SpaceWeatherData:
        if deep_space_mode:
            return await self._fallback(REASON_DEEP_SPACE)

        async with self._lock:
            entry = self._cache
            if entry and self._clock() - entry.stored_at < self._ttl:
                return self._from_entry(entry, DataSource.LIVE, None)
            if self._clock() < self._backoff_until:
                return await self._fallback(self._backoff_reason)  # don't hammer a failing API
            try:
                async with asyncio.timeout(self._fetch_timeout):
                    events = await self._client.fetch_events(self._start, self._end)
            except TimeoutError:
                log.warning("Live DONKI fetch exceeded %.0fs; serving fallback data", self._fetch_timeout)
                self._backoff_until = self._clock() + self._retry_after
                self._backoff_reason = REASON_UNAVAILABLE
                return await self._fallback(REASON_UNAVAILABLE)
            except DonkiError as exc:
                log.warning("Live DONKI fetch failed: %s", exc)
                limited = isinstance(exc, DonkiRateLimited)
                wait = max(self._retry_after, exc.retry_after or 0) if limited else self._retry_after
                self._backoff_until = self._clock() + wait
                self._backoff_reason = REASON_RATE_LIMITED if limited else REASON_UNAVAILABLE
                return await self._fallback(self._backoff_reason)
            self._backoff_until = 0.0
            self._cache = _CacheEntry(events, self._now(), self._clock())
            if self._db_cache is not None:
                await self._db_cache.put(
                    self._cache_key, [e.model_dump(mode="json") for e in events], self._cache.fetched_at
                )
            return self._from_entry(self._cache, DataSource.LIVE, None)

    @property
    def _cache_key(self) -> str:
        return f"donki:{self._start.isoformat()}:{self._end.isoformat()}"

    async def _fallback(self, reason: str) -> SpaceWeatherData:
        if self._cache:
            return self._from_entry(self._cache, DataSource.CACHED, reason)
        stored = await self._db_cache.get(self._cache_key) if self._db_cache is not None else None
        if stored is not None:
            payload, fetched_at = stored
            events = [SpaceWeatherEvent.model_validate(e) for e in payload]
            return SpaceWeatherData(source=DataSource.CACHED, data_as_of=fetched_at, reason=reason, events=events)
        return self.load_snapshot().model_copy(update={"reason": reason})

    @staticmethod
    def _from_entry(entry: _CacheEntry, source: DataSource, reason: str | None) -> SpaceWeatherData:
        return SpaceWeatherData(source=source, data_as_of=entry.fetched_at, reason=reason, events=entry.events)

"""Space-weather data with a 3-tier fallback: live -> in-memory cache -> snapshot file."""

import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from app.models.enums import DataSource
from app.models.space_weather import SpaceWeatherData, SpaceWeatherEvent
from app.services.donki_client import DonkiClient, DonkiError, DonkiRateLimited

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
        cache_ttl_seconds: int = 3600,
        retry_after_seconds: int = 60,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._start = window_start
        self._end = window_end
        self._snapshot_path = snapshot_path
        self._ttl = cache_ttl_seconds
        self._retry_after = retry_after_seconds
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
            return self._fallback(REASON_DEEP_SPACE)

        async with self._lock:
            entry = self._cache
            if entry and self._clock() - entry.stored_at < self._ttl:
                return self._from_entry(entry, DataSource.LIVE, None)
            if self._clock() < self._backoff_until:
                return self._fallback(self._backoff_reason)  # don't hammer a failing API
            try:
                events = await self._client.fetch_events(self._start, self._end)
            except DonkiError as exc:
                log.warning("Live DONKI fetch failed: %s", exc)
                limited = isinstance(exc, DonkiRateLimited)
                wait = max(self._retry_after, exc.retry_after or 0) if limited else self._retry_after
                self._backoff_until = self._clock() + wait
                self._backoff_reason = REASON_RATE_LIMITED if limited else REASON_UNAVAILABLE
                return self._fallback(self._backoff_reason)
            self._backoff_until = 0.0
            self._cache = _CacheEntry(events, self._now(), self._clock())
            return self._from_entry(self._cache, DataSource.LIVE, None)

    def _fallback(self, reason: str) -> SpaceWeatherData:
        if self._cache:
            return self._from_entry(self._cache, DataSource.CACHED, reason)
        return self.load_snapshot().model_copy(update={"reason": reason})

    @staticmethod
    def _from_entry(entry: _CacheEntry, source: DataSource, reason: str | None) -> SpaceWeatherData:
        return SpaceWeatherData(source=source, data_as_of=entry.fetched_at, reason=reason, events=entry.events)

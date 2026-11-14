"""Space-weather data with a 3-tier fallback: live -> in-memory cache -> snapshot file."""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from app.models.enums import DataSource
from app.models.space_weather import SpaceWeatherData, SpaceWeatherEvent
from app.services.donki_client import DonkiClient, DonkiError, DonkiRateLimited

log = logging.getLogger(__name__)


@dataclass
class _CacheEntry:
    events: list[SpaceWeatherEvent]
    fetched_at: datetime
    stored_at: float  # time.monotonic()


class SpaceWeatherService:
    def __init__(
        self,
        client: DonkiClient,
        window_start: date,
        window_end: date,
        snapshot_path: Path,
        cache_ttl_seconds: int = 3600,
        retry_after_seconds: int = 60,
    ):
        self._client = client
        self._start = window_start
        self._end = window_end
        self._snapshot_path = snapshot_path
        self._ttl = cache_ttl_seconds
        self._retry_after = retry_after_seconds
        self._failed_at: float | None = None  # monotonic time of last failed live call
        self._wait = retry_after_seconds  # how long to stay away after that failure
        self._failure_reason = "live_unavailable"
        self._cache: _CacheEntry | None = None
        self._lock = asyncio.Lock()
        self._snapshot: SpaceWeatherData | None = None

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
                events=[SpaceWeatherEvent.model_validate(e) for e in raw["events"]],
            )
        return self._snapshot

    async def get(self, deep_space_mode: bool = False) -> SpaceWeatherData:
        if deep_space_mode:
            return self._fallback("deep_space_mode")

        async with self._lock:
            entry = self._cache
            if entry and time.monotonic() - entry.stored_at < self._ttl:
                return self._from_entry(entry, DataSource.LIVE)
            if self._failed_at is not None and time.monotonic() - self._failed_at < self._wait:
                return self._fallback(self._failure_reason)  # don't hammer a failing API
            try:
                events = await self._client.fetch_events(self._start, self._end)
            except DonkiError as exc:
                log.warning("Live DONKI fetch failed: %s", exc)
                self._failed_at = time.monotonic()
                limited = isinstance(exc, DonkiRateLimited)
                self._failure_reason = "rate_limited" if limited else "live_unavailable"
                self._wait = max(self._retry_after, exc.retry_after or 0) if limited else self._retry_after
                return self._fallback(self._failure_reason)
            self._failed_at = None
            self._cache = _CacheEntry(events, datetime.now(timezone.utc), time.monotonic())
            return self._from_entry(self._cache, DataSource.LIVE)

    def _fallback(self, reason: str) -> SpaceWeatherData:
        if self._cache:
            return self._from_entry(self._cache, DataSource.CACHED, reason)
        snap = self.load_snapshot()
        return snap.model_copy(update={"reason": reason})

    @staticmethod
    def _from_entry(entry: _CacheEntry, source: DataSource, reason: str | None = None) -> SpaceWeatherData:
        return SpaceWeatherData(
            source=source, data_as_of=entry.fetched_at, reason=reason, events=entry.events
        )

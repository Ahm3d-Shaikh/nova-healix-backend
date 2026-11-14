"""Async client for the NASA DONKI space-weather API."""

import asyncio
import logging
from datetime import date
from typing import Any

import httpx

from app.models.space_weather import SpaceWeatherEvent
from app.services import donki_parsers as parsers

log = logging.getLogger(__name__)

RawFeed = list[dict[str, Any]]
FEEDS = ("SEP", "FLR", "CME", "GST", "notifications")
REQUIRED_FEEDS = ("SEP", "CME", "GST", "notifications")
RETRIES = 2  # extra attempts for transient failures (timeouts, 5xx)
RETRY_BACKOFF_SECONDS = 0.5
DEFAULT_RATE_LIMIT_WAIT = 900  # seconds, when NASA does not say how long


class DonkiError(Exception):
    """The live DONKI call could not be completed."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after  # hint for how long to stay away


class DonkiRateLimited(DonkiError):
    """api.nasa.gov rejected the key (HTTP 429 / OVER_RATE_LIMIT)."""


class DonkiClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        base_url: str,
        api_key: str,
        timeout: float = 15.0,
        backoff: float = RETRY_BACKOFF_SECONDS,
    ):
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._backoff = backoff
        self.rate_limit_remaining: int | None = None  # from X-RateLimit-Remaining

    async def _get(self, endpoint: str, start: date, end: date) -> RawFeed:
        params = {"startDate": start.isoformat(), "endDate": end.isoformat(), "api_key": self._api_key}
        url = f"{self._base_url}/{endpoint}"
        last = DonkiError(f"DONKI /{endpoint}: no attempt made")
        for attempt in range(RETRIES + 1):
            try:
                resp = await self._http.get(url, params=params, timeout=self._timeout)
            except httpx.HTTPError as exc:  # timeout, connection reset, DNS...
                last = DonkiError(f"DONKI /{endpoint} unreachable: {exc!r}")
            else:
                remaining = resp.headers.get("x-ratelimit-remaining")
                if remaining and remaining.isdigit():
                    self.rate_limit_remaining = int(remaining)
                if resp.status_code == 429 or (resp.status_code == 403 and "RATE_LIMIT" in resp.text):
                    raise DonkiRateLimited(
                        f"DONKI /{endpoint} rate limited (key {self._masked_key()})",
                        retry_after=_retry_after(resp),
                    )
                if resp.status_code >= 500:
                    last = DonkiError(f"DONKI /{endpoint} server error {resp.status_code}")
                elif resp.status_code >= 400:
                    # 4xx (e.g. 404 on /FLR) will not fix itself: don't retry.
                    raise DonkiError(f"DONKI /{endpoint} returned HTTP {resp.status_code}")
                else:
                    return self._json_list(endpoint, resp)
            if attempt < RETRIES:
                await asyncio.sleep(self._backoff * (attempt + 1))
        raise last

    @staticmethod
    def _json_list(endpoint: str, resp: httpx.Response) -> RawFeed:
        try:
            data = resp.json()
        except ValueError as exc:
            raise DonkiError(f"DONKI /{endpoint} returned invalid JSON") from exc
        if not isinstance(data, list):  # DONKI can return an error object with HTTP 200
            raise DonkiError(f"DONKI /{endpoint} returned an unexpected payload")
        return data

    def _masked_key(self) -> str:
        return "DEMO_KEY" if self._api_key == "DEMO_KEY" else "custom"

    async def fetch_events(self, start: date, end: date) -> list[SpaceWeatherEvent]:
        """Fetch + normalize all event types for [start, end] (inclusive).

        SEP, CME, GST and notifications are required: if any fails we raise so
        the caller falls back, rather than pretending partial data is live.
        Flares are best-effort - if /FLR fails we derive them from notifications.
        """
        results = await asyncio.gather(*(self._get(feed, start, end) for feed in FEEDS), return_exceptions=True)
        by_feed = dict(zip(FEEDS, results, strict=True))

        failures = [(name, by_feed[name]) for name in REQUIRED_FEEDS if isinstance(by_feed[name], BaseException)]
        if failures:
            limited = next((err for _, err in failures if isinstance(err, DonkiRateLimited)), None)
            if limited:
                raise limited
            name, err = failures[0]
            raise DonkiError(f"required DONKI feed {name} unavailable: {err}") from (
                err if isinstance(err, BaseException) else None
            )

        sep, cme, gst, notes = (_rows(by_feed[name]) for name in ("SEP", "CME", "GST", "notifications"))
        flr = by_feed["FLR"]
        if isinstance(flr, BaseException):
            log.warning("DONKI /FLR unavailable (%s); deriving flares from notifications", flr)
            flares = parsers.parse_flares_from_notifications(notes)
        else:
            flares = parsers.parse_flares(_rows(flr))

        events = [
            *parsers.parse_sep(sep),
            *flares,
            *parsers.parse_cme(cme),
            *parsers.parse_gst(gst),
            *parsers.parse_notifications(notes),
        ]
        return sorted((e for e in events if start <= e.time.date() <= end), key=lambda e: e.time)


def _rows(result: RawFeed | BaseException) -> RawFeed:
    """Narrow a gather() result that has already been checked for failure."""
    if isinstance(result, BaseException):  # pragma: no cover - guarded by the caller
        raise result
    return result


def _retry_after(resp: httpx.Response) -> float:
    value = resp.headers.get("retry-after", "")
    return float(value) if value.replace(".", "", 1).isdigit() else DEFAULT_RATE_LIMIT_WAIT

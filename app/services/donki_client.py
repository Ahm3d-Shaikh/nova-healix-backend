"""Async client for the NASA DONKI space-weather API."""

import asyncio
import logging
from datetime import date

import httpx

from app.models.space_weather import SpaceWeatherEvent
from app.services import donki_parsers as parsers

log = logging.getLogger(__name__)


class DonkiError(Exception):
    """The live DONKI call could not be completed."""


class DonkiClient:
    def __init__(self, http: httpx.AsyncClient, base_url: str, api_key: str, timeout: float = 15.0):
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    async def _get(self, endpoint: str, start: date, end: date) -> list[dict]:
        params = {"startDate": start.isoformat(), "endDate": end.isoformat(), "api_key": self._api_key}
        try:
            resp = await self._http.get(f"{self._base_url}/{endpoint}", params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise DonkiError(f"DONKI /{endpoint} failed: {exc}") from exc
        if not isinstance(data, list):  # DONKI returns an error object when rate-limited
            raise DonkiError(f"DONKI /{endpoint} returned an unexpected payload")
        return data

    async def fetch_events(self, start: date, end: date) -> list[SpaceWeatherEvent]:
        """Fetch + normalize all event types for [start, end] (inclusive).

        SEP, CME, GST and notifications are required: if any fails we raise so
        the caller falls back, rather than pretending partial data is live.
        Flares are best-effort — if /FLR fails we derive them from notifications.
        """
        sep, flr, cme, gst, notes = await asyncio.gather(
            self._get("SEP", start, end),
            self._get("FLR", start, end),
            self._get("CME", start, end),
            self._get("GST", start, end),
            self._get("notifications", start, end),
            return_exceptions=True,
        )
        for name, result in (("SEP", sep), ("CME", cme), ("GST", gst), ("notifications", notes)):
            if isinstance(result, BaseException):
                raise DonkiError(f"required DONKI feed {name} unavailable") from result

        if isinstance(flr, BaseException):
            log.warning("DONKI /FLR unavailable (%s); deriving flares from notifications", flr)
            flares = parsers.parse_flares_from_notifications(notes)
        else:
            flares = parsers.parse_flares(flr)

        events = [
            *parsers.parse_sep(sep),
            *flares,
            *parsers.parse_cme(cme),
            *parsers.parse_gst(gst),
            *parsers.parse_notifications(notes),
        ]
        in_window = [e for e in events if start <= e.time.date() <= end]
        return sorted(in_window, key=lambda e: e.time)

"""Async client for the NASA JPL Horizons ephemeris API (https://ssd-api.jpl.nasa.gov/doc/horizons.html).

We request a geocentric VECTORS table (VEC_TABLE=3) in CSV form, which gives, per time step,
the position/velocity plus one-way light time (LT, s), range (RG, km) and range rate (RR, km/s).
"""

import logging
from datetime import UTC, date, datetime
from typing import Any

import httpx

from app.nasa.models import DistanceSample

log = logging.getLogger(__name__)

EARTH_CENTER = "500@399"  # geocentre
# CSV columns: JDTDB, Calendar Date, X, Y, Z, VX, VY, VZ, LT, RG, RR
_COL_DATE, _COL_LT, _COL_RG, _COL_RR = 1, 8, 9, 10


class HorizonsError(Exception):
    """The live Horizons call could not be completed."""


class HorizonsClient:
    def __init__(self, http: httpx.AsyncClient, base_url: str, timeout: float = 20.0) -> None:
        self._http = http
        self._base_url = base_url
        self._timeout = timeout

    async def fetch_vectors(self, command: str, start: date, stop: date, step: str = "1 d") -> list[DistanceSample]:
        params = {
            "format": "json",
            "COMMAND": f"'{command}'",
            "CENTER": f"'{EARTH_CENTER}'",
            "EPHEM_TYPE": "'VECTORS'",
            "VEC_TABLE": "'3'",
            "CSV_FORMAT": "'YES'",
            "OUT_UNITS": "'KM-S'",
            "OBJ_DATA": "'NO'",
            "MAKE_EPHEM": "'YES'",
            "START_TIME": f"'{start.isoformat()}'",
            "STOP_TIME": f"'{stop.isoformat()}'",
            "STEP_SIZE": f"'{step}'",
        }
        try:
            resp = await self._http.get(self._base_url, params=params, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise HorizonsError(f"Horizons unreachable: {exc!r}") from exc
        if resp.status_code != 200:
            raise HorizonsError(f"Horizons returned HTTP {resp.status_code}")
        try:
            payload: dict[str, Any] = resp.json()
        except ValueError as exc:
            raise HorizonsError("Horizons returned invalid JSON") from exc
        if "error" in payload:
            raise HorizonsError(f"Horizons error: {str(payload['error'])[:200]}")
        return parse_vectors(str(payload.get("result", "")))


def parse_vectors(result: str) -> list[DistanceSample]:
    """Parse the $$SOE..$$EOE block of a CSV vector table."""
    start, end = result.find("$$SOE"), result.find("$$EOE")
    if start < 0 or end < 0:
        raise HorizonsError("Horizons response has no ephemeris table")
    samples = []
    for line in result[start + len("$$SOE") : end].strip().splitlines():
        cols = [c.strip() for c in line.split(",")]
        if len(cols) <= _COL_RR:
            continue
        try:
            when = datetime.strptime(cols[_COL_DATE].removeprefix("A.D. "), "%Y-%b-%d %H:%M:%S.%f").replace(tzinfo=UTC)
            samples.append(
                DistanceSample(
                    time=when,
                    light_time_s=float(cols[_COL_LT]),
                    distance_km=float(cols[_COL_RG]),
                    range_rate_km_s=float(cols[_COL_RR]),
                )
            )
        except ValueError:
            log.warning("Skipping unparseable Horizons row: %s", line[:120])
    if not samples:
        raise HorizonsError("Horizons ephemeris table is empty")
    return samples

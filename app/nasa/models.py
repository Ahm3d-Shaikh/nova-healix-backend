"""Shapes shared by the NASA feeds: DONKI space weather and JPL Horizons ephemeris samples."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class DataSource(StrEnum):
    """Where a feed's data came from: live API, last good copy, or the bundled real snapshot."""

    LIVE = "live"
    CACHED = "cached"
    SNAPSHOT = "snapshot"


class EventKind(StrEnum):
    SEP = "sep"
    FLARE = "flare"
    CME = "cme"
    GEOSTORM = "geostorm"
    NOTIFICATION = "notification"


class SpaceWeatherEvent(BaseModel):
    id: str
    kind: EventKind
    time: datetime
    summary: str
    class_type: str | None = None  # flares, e.g. "X2.2"
    speed_km_s: float | None = None  # CMEs
    kp_index: float | None = None  # geomagnetic storms
    link: str | None = None


class SpaceWeatherData(BaseModel):
    """Result of a DONKI refresh: events plus where they came from."""

    source: DataSource
    data_as_of: datetime
    reason: str | None = None
    events: list[SpaceWeatherEvent]


class DistanceSample(BaseModel):
    """One JPL Horizons vector-table row (target relative to Earth's centre)."""

    time: datetime
    distance_km: float
    light_time_s: float  # one-way light time
    range_rate_km_s: float  # + = moving away from Earth

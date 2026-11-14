from datetime import date, datetime

from pydantic import BaseModel

from app.models.enums import DataSource, EventKind


class SpaceWeatherEvent(BaseModel):
    id: str
    kind: EventKind
    time: datetime
    summary: str
    class_type: str | None = None  # flares, e.g. "X2.2"
    speed_km_s: float | None = None  # CMEs
    kp_index: float | None = None  # geomagnetic storms
    link: str | None = None


class MissionEvent(SpaceWeatherEvent):
    mission_day: int


class SpaceWeatherResponse(BaseModel):
    source: DataSource
    data_as_of: datetime
    reason: str | None = None  # why we are not serving live data
    window_start: date
    window_end: date
    events: list[MissionEvent]


class SpaceWeatherData(BaseModel):
    """Service-level result (events without mission-day mapping)."""

    source: DataSource
    data_as_of: datetime
    reason: str | None = None
    events: list[SpaceWeatherEvent]

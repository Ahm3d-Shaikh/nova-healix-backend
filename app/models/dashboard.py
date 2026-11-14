from datetime import datetime

from pydantic import BaseModel

from app.models.alert import CrewAlert
from app.models.crew import DashboardCrew
from app.models.enums import DataSource
from app.models.settings import MissionSettingsResponse
from app.models.space_weather import MissionEvent


class SpaceWeatherStatus(BaseModel):
    source: DataSource
    data_as_of: datetime
    reason: str | None
    events_last_24h: list[MissionEvent]  # SEP / flare / CME / storm events only


class DashboardResponse(BaseModel):
    day: int
    mission_days: int
    settings: MissionSettingsResponse
    space_weather: SpaceWeatherStatus
    crew: list[DashboardCrew]
    alerts: list[CrewAlert]  # worst first

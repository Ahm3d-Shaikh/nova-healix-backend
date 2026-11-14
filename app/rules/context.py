from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.models.crew import DailyRecord
from app.models.enums import DataSource, Mission
from app.models.space_weather import SpaceWeatherEvent


@dataclass(frozen=True)
class RuleContext:
    """Everything a rule may look at. `records` hold mission days 1..day."""

    day: int
    now: datetime  # end of mission day `day`
    records: Sequence[DailyRecord]
    events: Sequence[SpaceWeatherEvent]
    weather_source: DataSource
    weather_as_of: datetime
    deep_space_mode: bool
    mission: Mission

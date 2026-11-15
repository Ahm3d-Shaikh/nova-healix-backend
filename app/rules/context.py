from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.models.crew import DailyRecord
from app.models.distance import DistanceSample
from app.models.enums import DataSource, Mission
from app.models.mobility import MobilityCheck
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
    # JPL Horizons geometry for the end of `day` (None when unavailable)
    distance: DistanceSample | None = None
    distance_target: str | None = None
    distance_source: DataSource | None = None
    distance_as_of: datetime | None = None
    # Mobility & Balance checks done on mission days 1..day, oldest first
    mobility: Sequence[MobilityCheck] = ()

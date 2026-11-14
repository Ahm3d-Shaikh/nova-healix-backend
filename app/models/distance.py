from datetime import datetime

from pydantic import BaseModel

from app.models.enums import DataSource, Mission


class DistanceSample(BaseModel):
    """One JPL Horizons vector-table row (target relative to Earth's centre)."""

    time: datetime
    distance_km: float
    light_time_s: float  # one-way light time
    range_rate_km_s: float  # + = moving away from Earth


class DistanceData(BaseModel):
    mission: Mission
    target: str  # Horizons COMMAND id
    target_name: str
    source: DataSource
    data_as_of: datetime
    reason: str | None
    samples: list[DistanceSample]

    def at(self, moment: datetime) -> DistanceSample | None:
        """Latest sample at or before `moment` (first sample if `moment` is earlier)."""
        if not self.samples:
            return None
        before = [s for s in self.samples if s.time <= moment]
        return before[-1] if before else self.samples[0]


class DistancePoint(BaseModel):
    day: int
    distance_km: float
    light_time_s: float


class DistanceResponse(BaseModel):
    mission: Mission
    target_name: str
    source: DataSource
    data_as_of: datetime
    reason: str | None
    days: list[DistancePoint]

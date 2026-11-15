"""The mission clock: every time in the API is a mission hour (float hours since launch)."""

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from app.domain.mission_plan import (
    CURRENT_DAY,
    DAY_MS,
    GENERATED_DAYS,
    HOUR_MS,
    MISSION_DURATION_DAYS,
    distance_au_on_day,
)


@dataclass
class Trajectory:
    """Earth-ship distance per mission day (AU). Replaced by JPL Horizons data when it is available."""

    au: list[float] = field(
        default_factory=lambda: [distance_au_on_day(i + 1) for i in range(MISSION_DURATION_DAYS + 1)]
    )
    source: str = "model"
    as_of: datetime | None = None  # when the real arrival distance was fetched


class MissionClock:
    def __init__(self, launch_epoch_ms: int, now_ms: Callable[[], float] | None = None) -> None:
        self.launch_epoch_ms = launch_epoch_ms
        self._now_ms = now_ms or (lambda: time.time() * 1000)

    @staticmethod
    def default_launch_epoch_ms(now_ms: float) -> int:
        """Launch epoch chosen so that 'now' falls on CURRENT_DAY (with the real UTC time of day)."""
        midnight = math.floor(now_ms / DAY_MS) * DAY_MS
        return int(midnight - (CURRENT_DAY - 1) * DAY_MS)

    def now_hour(self) -> float:
        """Exact current mission hour."""
        return (self._now_ms() - self.launch_epoch_ms) / HOUR_MS

    def quarter_hour(self) -> float:
        """Current mission hour, quarter-hour aligned so new data shows up in the current analysis."""
        return math.floor(self.now_hour() * 4) / 4

    def current_day(self) -> int:
        return max(1, min(GENERATED_DAYS, math.floor(self.now_hour() / 24) + 1))

    def clamp(self, at: float | None) -> float:
        """Evaluation hour: 'now' when missing, never later than now, never before launch."""
        now = self.now_hour()
        return now if at is None else max(0.0, min(at, now))

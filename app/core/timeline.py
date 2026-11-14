"""Maps real-world timestamps onto the simulated mission timeline."""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class MissionTimeline:
    start: datetime  # UTC midnight at the start of mission day 1
    days: int

    def day_start(self, day: int) -> datetime:
        return self.start + timedelta(days=day - 1)

    def day_end(self, day: int) -> datetime:
        """End of mission day `day`; the 'now' used by the rules."""
        return self.start + timedelta(days=day)

    def day_of(self, moment: datetime) -> int:
        return (moment - self.start).days + 1

    def clamp(self, day: int) -> int:
        return max(1, min(self.days, day))

"""Maps real-world timestamps onto the simulated mission timeline."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.errors import InvalidDayError


@dataclass(frozen=True)
class MissionTimeline:
    start: datetime  # UTC midnight at the start of mission day 1
    days: int

    def day_end(self, day: int) -> datetime:
        """End of mission day `day`; the 'now' used by the rules."""
        return self.start + timedelta(days=day)

    def day_of(self, moment: datetime) -> int:
        return (moment - self.start).days + 1

    def validate(self, day: int) -> int:
        if not 1 <= day <= self.days:
            raise InvalidDayError(day, self.days)
        return day

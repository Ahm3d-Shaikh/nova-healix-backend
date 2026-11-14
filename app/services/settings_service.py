from app.core.errors import InvalidDayError
from app.models.settings import MissionSettings


class SettingsService:
    """In-memory demo settings (mission, deep space mode, current day)."""

    def __init__(self, mission_days: int):
        self.mission_days = mission_days
        self._settings = MissionSettings()

    def get(self) -> MissionSettings:
        return self._settings

    def update(self, new: MissionSettings) -> MissionSettings:
        if new.current_day > self.mission_days:
            raise InvalidDayError(new.current_day, self.mission_days)
        self._settings = new
        return self._settings

    def reset(self) -> MissionSettings:
        self._settings = MissionSettings()
        return self._settings

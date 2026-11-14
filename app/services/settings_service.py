from app.models.settings import MissionSettings


class SettingsService:
    """In-memory demo settings (mission, deep space mode, current day)."""

    def __init__(self, mission_days: int):
        self.mission_days = mission_days
        self._settings = MissionSettings()

    def get(self) -> MissionSettings:
        return self._settings

    def update(self, new: MissionSettings) -> MissionSettings:
        self._settings = new.model_copy(update={"current_day": min(new.current_day, self.mission_days)})
        return self._settings

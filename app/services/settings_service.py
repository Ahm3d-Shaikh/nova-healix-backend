from app.core.errors import InvalidDayError
from app.models.settings import MissionSettings
from app.repositories.settings import SettingsRepository


class SettingsService:
    """Demo settings (mission, deep space mode, current day), persisted in the database."""

    def __init__(self, mission_days: int, repo: SettingsRepository):
        self.mission_days = mission_days
        self._repo = repo

    async def get(self) -> MissionSettings:
        return await self._repo.get() or MissionSettings()

    async def update(self, new: MissionSettings) -> MissionSettings:
        if not 1 <= new.current_day <= self.mission_days:
            raise InvalidDayError(new.current_day, self.mission_days)
        await self._repo.save(new)
        return new

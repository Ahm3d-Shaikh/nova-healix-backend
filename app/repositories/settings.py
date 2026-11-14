from datetime import UTC, datetime

from app.db.base import Database
from app.models.settings import MissionSettings

MISSION_SETTINGS = "mission_settings"
SINGLETON_ID = 1  # one settings row for the whole deployment


class SettingsRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def get(self) -> MissionSettings | None:
        rows = await self._db.table(MISSION_SETTINGS).select(eq={"id": SINGLETON_ID}, limit=1)
        return MissionSettings.model_validate(rows[0]) if rows else None

    async def save(self, settings: MissionSettings) -> None:
        row = {"id": SINGLETON_ID, **settings.model_dump(mode="json"), "updated_at": datetime.now(UTC).isoformat()}
        await self._db.table(MISSION_SETTINGS).upsert([row], on_conflict="id")

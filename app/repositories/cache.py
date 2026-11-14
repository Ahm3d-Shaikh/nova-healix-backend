"""Last-good copies of external API data (DONKI, Horizons), so a restart doesn't lose them."""

from datetime import UTC, datetime
from typing import Any

from app.db.base import Database, DatabaseError

EXTERNAL_DATA_CACHE = "external_data_cache"


class CacheRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def get(self, key: str) -> tuple[Any, datetime] | None:
        """(payload, fetched_at), or None when missing or the database is unreachable."""
        try:
            rows = await self._db.table(EXTERNAL_DATA_CACHE).select(eq={"key": key}, limit=1)
        except DatabaseError:
            return None  # the cache is best-effort; callers fall back to the bundled snapshot
        if not rows:
            return None
        return rows[0]["payload"], datetime.fromisoformat(rows[0]["fetched_at"])

    async def put(self, key: str, payload: Any, fetched_at: datetime) -> None:
        try:
            await self._db.table(EXTERNAL_DATA_CACHE).upsert(
                [
                    {
                        "key": key,
                        "payload": payload,
                        "fetched_at": fetched_at.isoformat(),
                        "updated_at": datetime.now(UTC).isoformat(),
                    }
                ],
                on_conflict="key",
            )
        except DatabaseError:
            return  # best-effort

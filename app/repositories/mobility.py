import uuid
from datetime import UTC, datetime

from app.db.base import Database
from app.models.mobility import MobilityCheck, MobilityMeasurements

CHECKS = "mobility_checks"


class MobilityRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(self, astronaut_id: str, day: int, m: MobilityMeasurements, reliable: bool) -> MobilityCheck:
        row = await self._db.table(CHECKS).insert(
            {
                "id": str(uuid.uuid4()),
                "astronaut_id": astronaut_id,
                "mission_day": day,
                "created_at": datetime.now(UTC).isoformat(),
                **m.model_dump(),
                "reliable": reliable,
            }
        )
        return _check(row)

    async def checks(self, astronaut_id: str | None = None) -> list[MobilityCheck]:
        """Oldest first; every astronaut when `astronaut_id` is None."""
        eq = {"astronaut_id": astronaut_id} if astronaut_id else None
        rows = await self._db.table(CHECKS).select(eq=eq, order="created_at")
        return [_check(r) for r in rows]


def _check(row: dict) -> MobilityCheck:  # type: ignore[type-arg]
    return MobilityCheck(
        id=row["id"],
        astronaut_id=row["astronaut_id"],
        mission_day=row["mission_day"],
        created_at=row["created_at"],
        measurements=MobilityMeasurements.model_validate({k: row[k] for k in MobilityMeasurements.model_fields}),
        reliable=row["reliable"],
    )

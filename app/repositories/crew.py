from collections import defaultdict

from app.db.base import Database
from app.models.crew import Astronaut, DailyRecord

ASTRONAUTS = "astronauts"
DAILY_RECORDS = "daily_records"

# Stored columns (computed fields and overlay-only fields are not persisted).
RECORD_COLUMNS = (
    "day",
    "sleep_hours",
    "resting_hr",
    "sys_bp",
    "dia_bp",
    "exercise_min",
    "co2_mmhg_1h",
    "co2_mmhg_7d",
    "cabin_temp_c",
    "loneliness_q1",
    "loneliness_q2",
    "loneliness_q3",
    "self_rating",
    "pvt_mean_rt",
    "pvt_mean_speed",
    "pvt_lapses",
    "pvt_false_starts",
    "dose_msv",
)


class CrewRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def astronauts(self) -> list[Astronaut]:
        rows = await self._db.table(ASTRONAUTS).select(order="id")
        return [Astronaut.model_validate(r) for r in rows]

    async def records(self) -> dict[str, list[DailyRecord]]:
        rows = await self._db.table(DAILY_RECORDS).select(order="day")
        out: defaultdict[str, list[DailyRecord]] = defaultdict(list)
        for r in rows:
            out[r["astronaut_id"]].append(DailyRecord.model_validate({k: r[k] for k in RECORD_COLUMNS}))
        return dict(out)

    async def seed(self, roster: list[Astronaut], records: dict[str, list[DailyRecord]]) -> None:
        await self._db.table(ASTRONAUTS).upsert([a.model_dump(mode="json") for a in roster], on_conflict="id")
        rows = [
            {
                "astronaut_id": astro_id,
                "source": "simulated",
                **rec.model_dump(mode="json", include=set(RECORD_COLUMNS)),
            }
            for astro_id, recs in records.items()
            for rec in recs
        ]
        await self._db.table(DAILY_RECORDS).upsert(rows, on_conflict="astronaut_id,day")

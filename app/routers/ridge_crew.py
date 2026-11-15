from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import RidgeDep
from app.models.alert import CrewAlert
from app.models.crew import AstronautSummary, CrewDetail

router = APIRouter(prefix="/api", tags=["ridge"])
DayQuery = Annotated[int | None, Query(ge=1, description="Mission day (defaults to the current setting)")]


@router.get("/ridge/crew")
async def list_crew(c: RidgeDep, day: DayQuery = None) -> list[AstronautSummary]:
    return await c.crew.summaries(day)


@router.get("/ridge/crew/{astronaut_id}")
async def crew_detail(astronaut_id: str, c: RidgeDep, day: DayQuery = None) -> CrewDetail:
    return await c.crew.detail(astronaut_id, day)


@router.get("/alerts", summary="All amber/red alerts across the crew")
async def alerts(c: RidgeDep, day: DayQuery = None) -> list[CrewAlert]:
    return await c.crew.alerts(day)

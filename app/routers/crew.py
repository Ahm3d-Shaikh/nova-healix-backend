from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ContainerDep
from app.models.alert import CrewAlert
from app.models.crew import AstronautSummary, CrewDetail

router = APIRouter(prefix="/api", tags=["crew"])
DayQuery = Annotated[int | None, Query(ge=1, description="Mission day (defaults to the current setting)")]


@router.get("/crew")
async def list_crew(c: ContainerDep, day: DayQuery = None) -> list[AstronautSummary]:
    return await c.crew.summaries(day)


@router.get("/crew/{astronaut_id}")
async def crew_detail(astronaut_id: str, c: ContainerDep, day: DayQuery = None) -> CrewDetail:
    return await c.crew.detail(astronaut_id, day)


@router.get("/alerts", summary="All amber/red alerts across the crew")
async def alerts(c: ContainerDep, day: DayQuery = None) -> list[CrewAlert]:
    return await c.crew.alerts(day)

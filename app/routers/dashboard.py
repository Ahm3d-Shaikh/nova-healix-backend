from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ContainerDep
from app.models.crew import TimelineResponse
from app.models.dashboard import DashboardResponse
from app.routers.crew import DayQuery

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard", summary="Everything for the main dashboard")
async def dashboard(c: ContainerDep, day: DayQuery = None) -> DashboardResponse:
    """Settings, data-source status, every astronaut's six cards (levels + metrics + rule
    results) and the crew alert panel, for one mission day, in a single call."""
    return await c.crew.dashboard(day)


@router.get("/timeline", summary="Card levels for all mission days")
async def timeline(
    c: ContainerDep,
    astronaut: Annotated[str | None, Query(description="Limit to one astronaut id")] = None,
) -> TimelineResponse:
    """Powers the mission-day slider and per-hazard history charts without 30 requests."""
    return await c.crew.timeline_all(astronaut)

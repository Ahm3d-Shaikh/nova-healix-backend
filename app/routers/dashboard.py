from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_container
from app.container import Container
from app.models.crew import TimelineResponse
from app.models.dashboard import DashboardResponse
from app.services.crew_service import UnknownAstronaut

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardResponse, summary="Everything for the main dashboard")
async def dashboard(day: int | None = Query(None, ge=1), c: Container = Depends(get_container)):
    """Settings, data-source status, every astronaut's six cards (levels + metrics + rule
    results) and the crew alert panel, for one mission day, in a single call."""
    return await c.crew.dashboard(day)


@router.get("/timeline", response_model=TimelineResponse, summary="Card levels for all 30 days")
async def timeline(astronaut: str | None = Query(None, description="Limit to one astronaut id"),
                   c: Container = Depends(get_container)):
    """Powers the mission-day slider and per-hazard history charts without 30 requests."""
    try:
        return await c.crew.timeline_all(astronaut)
    except UnknownAstronaut:
        raise HTTPException(404, f"Unknown astronaut '{astronaut}'") from None

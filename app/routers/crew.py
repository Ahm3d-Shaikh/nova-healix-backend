from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_container
from app.container import Container
from app.models.alert import CrewAlert
from app.models.crew import AstronautSummary, CrewDetail
from app.services.crew_service import UnknownAstronaut

router = APIRouter(prefix="/api", tags=["crew"])
DAY = Query(None, ge=1, description="Mission day (defaults to the current setting)")


@router.get("/crew", response_model=list[AstronautSummary])
async def list_crew(day: int | None = DAY, c: Container = Depends(get_container)):
    return await c.crew.summaries(day)


@router.get("/crew/{astronaut_id}", response_model=CrewDetail)
async def crew_detail(astronaut_id: str, day: int | None = DAY, c: Container = Depends(get_container)):
    try:
        return await c.crew.detail(astronaut_id, day)
    except UnknownAstronaut:
        raise HTTPException(404, f"Unknown astronaut '{astronaut_id}'") from None


@router.get("/alerts", response_model=list[CrewAlert], summary="All amber/red alerts across the crew")
async def alerts(day: int | None = DAY, c: Container = Depends(get_container)):
    return await c.crew.alerts(day)

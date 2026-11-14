from fastapi import APIRouter

from app.api.deps import ContainerDep
from app.models.dashboard import DashboardResponse
from app.routers.crew import DayQuery

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard", summary="Everything for the main dashboard")
async def dashboard(c: ContainerDep, day: DayQuery = None) -> DashboardResponse:
    """Settings, data-source status, every astronaut's six cards (levels + metrics + rule
    results) and the crew alert panel, for one mission day, in a single call."""
    return await c.crew.dashboard(day)

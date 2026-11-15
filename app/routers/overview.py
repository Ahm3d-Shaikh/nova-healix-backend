from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ContainerDep
from app.schemas.assessment import Insight
from app.schemas.overview import Dashboard, DistanceResponse

router = APIRouter(prefix="/api", tags=["overview"])

At = Annotated[float | None, Query(description="Mission hour to evaluate (default now; never later than now)")]
Autonomous = Annotated[bool, Query(description="true while the Earth link is lost in the simulation")]


@router.get("/distance")
async def distance(c: ContainerDep) -> DistanceResponse:
    """Earth distance and one-way signal delay for every mission day (real NASA JPL Horizons at the Mars end)."""
    return c.overview.distance()


@router.get("/dashboard")
async def dashboard(c: ContainerDep, at: At = None, autonomous: Autonomous = False) -> Dashboard:
    """Everything for one overview screen in a single call: link, space events, 5 hazards and findings per astronaut."""
    return c.overview.dashboard(at, autonomous)


@router.get("/alerts")
async def alerts(c: ContainerDep, at: At = None, autonomous: Autonomous = False) -> list[Insight]:
    """Active findings at watch or alert severity across the crew, most urgent first."""
    return c.overview.alerts(at, autonomous)

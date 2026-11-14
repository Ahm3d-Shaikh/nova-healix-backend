from fastapi import APIRouter, status

from app.api.deps import ContainerDep
from app.models.mobility import MobilityHistory, MobilityMeasurements, MobilityMethod, MobilitySubmission
from app.routers.crew import DayQuery
from app.services.mobility_service import METHOD

router = APIRouter(prefix="/api/mobility", tags=["mobility"])


@router.get("/method")
async def method() -> MobilityMethod:
    """The 3 short tests, what to send, thresholds, and what the check cannot do."""
    return METHOD


@router.post("/{astronaut_id}", status_code=status.HTTP_201_CREATED)
async def submit_check(
    astronaut_id: str, body: MobilityMeasurements, c: ContainerDep, day: DayQuery = None
) -> MobilitySubmission:
    """Save a Mobility & Balance Check measured in the browser; it feeds the Gravity card."""
    return await c.mobility.submit(astronaut_id, await c.crew.resolve_day(day), body)


@router.get("/{astronaut_id}")
async def history(astronaut_id: str, c: ContainerDep) -> MobilityHistory:
    return await c.mobility.history(astronaut_id)

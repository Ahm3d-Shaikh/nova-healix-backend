from fastapi import APIRouter, status

from app.api.deps import ContainerDep
from app.schemas.mobility import MobilityHistory, MobilityMeasurements, MobilityMethod, MobilitySubmission
from app.services.mobility import METHOD

router = APIRouter(prefix="/api/mobility", tags=["mobility"])


@router.get("/method")
async def method() -> MobilityMethod:
    """The 3 short tests, what to send, thresholds, and what the check cannot do."""
    return METHOD


@router.post("/{crew_id}", status_code=status.HTTP_201_CREATED)
async def submit_check(crew_id: str, body: MobilityMeasurements, c: ContainerDep) -> MobilitySubmission:
    """Save a check measured in the browser. It feeds the Gravity hazard score and the findings automatically."""
    return await c.mobility.submit(crew_id, body)


@router.get("/{crew_id}")
async def history(crew_id: str, c: ContainerDep) -> MobilityHistory:
    return c.mobility.history(crew_id)

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import ContainerDep
from app.schemas.telemetry import Baseline, CheckIn, CheckInDraft, LiveVitals, Sample

router = APIRouter(prefix="/api/crew", tags=["telemetry"])

From = Annotated[float, Query(alias="from", description="Mission hour")]
To = Annotated[float, Query(alias="to", description="Mission hour (clamped to now)")]


@router.get("/{crew_id}/metrics/{metric}")
async def series(
    crew_id: str,
    metric: str,
    c: ContainerDep,
    start: From,
    end: To,
    bucket: Annotated[
        float, Query(ge=1, le=24 * 30, description="Hours per bucket; >1 returns the mean per bucket")
    ] = 1,
) -> list[Sample]:
    return c.telemetry.series(crew_id, metric, start, end, bucket)


@router.get("/{crew_id}/metrics/{metric}/baseline")
async def baseline(crew_id: str, metric: str, c: ContainerDep) -> Baseline | None:
    """The astronaut's personal normal range from their own data; null when none is meaningful."""
    return c.telemetry.baseline(crew_id, metric)


@router.get("/{crew_id}/vitals/live")
async def live(crew_id: str, c: ContainerDep) -> LiveVitals:
    return c.telemetry.live(crew_id)


@router.get("/{crew_id}/checkins")
async def check_ins(crew_id: str, c: ContainerDep, start: From, end: To) -> list[CheckIn]:
    return c.telemetry.check_ins(crew_id, start, end)


@router.post("/{crew_id}/checkins", status_code=status.HTTP_201_CREATED, tags=["crew-mode"])
async def submit_check_in(crew_id: str, body: CheckInDraft, c: ContainerDep) -> CheckIn:
    """One check-in per astronaut per day; a second one on the same day replaces the first."""
    return await c.crew_mode.submit_check_in(crew_id, body)

from fastapi import APIRouter

from app.api.deps import ContainerDep
from app.models.mirror_gap import MirrorGapHistory, MirrorGapResult, MirrorGapSubmission
from app.routers.crew import DayQuery

router = APIRouter(prefix="/api/mirror-gap", tags=["mirror gap"])


@router.post("/{astronaut_id}")
async def submit(
    astronaut_id: str, body: MirrorGapSubmission, c: ContainerDep, day: DayQuery = None
) -> MirrorGapResult:
    return c.mirror_gap.submit(astronaut_id, body, c.crew.resolve_day(day))


@router.get("/{astronaut_id}")
async def history(astronaut_id: str, c: ContainerDep) -> MirrorGapHistory:
    return c.mirror_gap.history(astronaut_id)

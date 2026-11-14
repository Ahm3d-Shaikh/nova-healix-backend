from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_container
from app.container import Container
from app.models.mirror_gap import MirrorGapHistory, MirrorGapResult, MirrorGapSubmission
from app.services.crew_service import UnknownAstronaut
from app.services.mirror_gap_service import NoValidResponses

router = APIRouter(prefix="/api/mirror-gap", tags=["mirror gap"])


@router.post("/{astronaut_id}", response_model=MirrorGapResult)
async def submit(astronaut_id: str, body: MirrorGapSubmission, c: Container = Depends(get_container)):
    try:
        return c.mirror_gap.submit(astronaut_id, body)
    except UnknownAstronaut:
        raise HTTPException(404, f"Unknown astronaut '{astronaut_id}'") from None
    except NoValidResponses as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("/{astronaut_id}", response_model=MirrorGapHistory)
async def history(astronaut_id: str, c: Container = Depends(get_container)):
    try:
        return c.mirror_gap.history(astronaut_id)
    except UnknownAstronaut:
        raise HTTPException(404, f"Unknown astronaut '{astronaut_id}'") from None

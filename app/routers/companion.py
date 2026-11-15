from fastapi import APIRouter, status

from app.api.deps import ContainerDep
from app.schemas.nova import CompanionRequest, CompanionTurn, SharedNote, SharedNoteBody

router = APIRouter(prefix="/api/crew", tags=["nova"])


@router.post("/{crew_id}/companion/reply")
async def reply(crew_id: str, body: CompanionRequest, c: ContainerDep) -> CompanionTurn:
    """Stateless: omit `text` for the greeting. The request and reply are never stored or logged."""
    return await c.companion.reply(crew_id, body)


@router.post("/{crew_id}/shared-notes", status_code=status.HTTP_201_CREATED)
async def share_note(crew_id: str, body: SharedNoteBody, c: ContainerDep) -> SharedNote:
    """Only called after the astronaut confirms a share card. Becomes a `note:<id>` finding."""
    return await c.companion.share_note(crew_id, body.text)

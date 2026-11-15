from fastapi import APIRouter

from app.api.deps import ContainerDep
from app.schemas.crewmode import Assignment, ProgressBody, Questionnaire, SubmitBody

router = APIRouter(prefix="/api", tags=["crew-mode"])


@router.get("/questionnaires")
async def questionnaires(c: ContainerDep) -> dict[str, Questionnaire]:
    return c.crew_mode.questionnaires()


@router.get("/crew/{crew_id}/assignments")
async def assignments(crew_id: str, c: ContainerDep) -> list[Assignment]:
    return c.crew_mode.assignments(crew_id)


@router.get("/assignments/{assignment_id}")
async def assignment(assignment_id: str, c: ContainerDep) -> Assignment:
    return c.crew_mode.assignment(assignment_id)


@router.put("/assignments/{assignment_id}/progress")
async def save_progress(assignment_id: str, body: ProgressBody, c: ContainerDep) -> Assignment:
    """Save answers so the questionnaire can be resumed; status becomes in-progress."""
    return await c.crew_mode.save_progress(assignment_id, body.answers, body.current_index)


@router.post("/assignments/{assignment_id}/submit")
async def submit(assignment_id: str, body: SubmitBody, c: ContainerDep) -> Assignment:
    """Score 0-100 (higher = more strain); feeds `stress` / `workload` where it applies. 409 if already done."""
    return await c.crew_mode.submit(assignment_id, body.answers)

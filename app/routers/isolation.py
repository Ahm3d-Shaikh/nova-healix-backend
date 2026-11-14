from fastapi import APIRouter

from app.api.deps import ContainerDep
from app.models.isolation import IsolationHistory, IsolationResult, IsolationSubmission, Questionnaire
from app.routers.crew import DayQuery
from app.services.isolation_service import QUESTIONNAIRE

router = APIRouter(prefix="/api/isolation", tags=["isolation"])


@router.get("/questionnaire")
async def questionnaire() -> Questionnaire:
    """Questions, answer options and bands for the Angular check-in form."""
    return QUESTIONNAIRE


@router.post("/{astronaut_id}")
async def submit(
    astronaut_id: str, body: IsolationSubmission, c: ContainerDep, day: DayQuery = None
) -> IsolationResult:
    return c.isolation.submit(astronaut_id, body, c.crew.resolve_day(day))


@router.get("/{astronaut_id}")
async def history(astronaut_id: str, c: ContainerDep) -> IsolationHistory:
    return c.isolation.history(astronaut_id)

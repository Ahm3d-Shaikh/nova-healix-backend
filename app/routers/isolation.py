from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_container
from app.container import Container
from app.models.isolation import IsolationHistory, IsolationResult, IsolationSubmission, Questionnaire
from app.services.crew_service import UnknownAstronaut
from app.services.isolation_service import QUESTIONNAIRE

router = APIRouter(prefix="/api/isolation", tags=["isolation"])


@router.get("/questionnaire", response_model=Questionnaire)
async def questionnaire():
    """Questions, answer options and bands for the Angular check-in form."""
    return QUESTIONNAIRE


@router.post("/{astronaut_id}", response_model=IsolationResult)
async def submit(astronaut_id: str, body: IsolationSubmission, c: Container = Depends(get_container)):
    try:
        return c.isolation.submit(astronaut_id, body)
    except UnknownAstronaut:
        raise HTTPException(404, f"Unknown astronaut '{astronaut_id}'") from None


@router.get("/{astronaut_id}", response_model=IsolationHistory)
async def history(astronaut_id: str, c: Container = Depends(get_container)):
    try:
        return c.isolation.history(astronaut_id)
    except UnknownAstronaut:
        raise HTTPException(404, f"Unknown astronaut '{astronaut_id}'") from None

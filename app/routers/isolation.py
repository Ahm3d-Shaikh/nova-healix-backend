from fastapi import APIRouter, status

from app.api.deps import RidgeDep
from app.models.isolation import (
    ChatMessageIn,
    ChatSessionDetail,
    ChatTurnResponse,
    IsolationHistory,
    LonelinessAssessment,
    ScoringMethod,
    StartSessionResponse,
)
from app.routers.ridge_crew import DayQuery
from app.services.isolation_service import METHOD

router = APIRouter(prefix="/api/isolation", tags=["isolation"])


@router.get("/method")
async def method() -> ScoringMethod:
    """How the AI check-in is scored: instrument, item scale, thresholds and turn limits."""
    return METHOD


@router.post("/{astronaut_id}/sessions", status_code=status.HTTP_201_CREATED)
async def start_session(astronaut_id: str, c: RidgeDep, day: DayQuery = None) -> StartSessionResponse:
    """Open today's check-in chat; returns the companion's opening message."""
    return await c.isolation.start(astronaut_id, await c.crew.resolve_day(day))


@router.post("/{astronaut_id}/sessions/{session_id}/messages")
async def send_message(astronaut_id: str, session_id: str, body: ChatMessageIn, c: RidgeDep) -> ChatTurnResponse:
    """Send what the astronaut said; returns the companion's reply."""
    return await c.isolation.send(astronaut_id, session_id, body.content)


@router.post("/{astronaut_id}/sessions/{session_id}/complete")
async def complete_session(astronaut_id: str, session_id: str, c: RidgeDep) -> LonelinessAssessment:
    """Score the chat: loneliness score (3-9), level, alert. Idempotent."""
    return await c.isolation.complete(astronaut_id, session_id)


@router.get("/{astronaut_id}/sessions/{session_id}")
async def session_detail(astronaut_id: str, session_id: str, c: RidgeDep) -> ChatSessionDetail:
    return await c.isolation.detail(astronaut_id, session_id)


@router.get("/{astronaut_id}")
async def history(astronaut_id: str, c: RidgeDep) -> IsolationHistory:
    """Loneliness score per day: simulated baseline plus every AI check-in."""
    return await c.isolation.history(astronaut_id)

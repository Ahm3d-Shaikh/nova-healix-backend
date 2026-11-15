from fastapi import APIRouter, status

from app.api.deps import ContainerDep
from app.schemas.echo import (
    EchoHistory,
    EchoMessageIn,
    EchoMethod,
    EchoSessionDetail,
    EchoTurnResponse,
    LonelinessAssessment,
    StartEchoResponse,
)
from app.services.echo import METHOD

router = APIRouter(prefix="/api/isolation", tags=["echo"])


@router.get("/method")
async def method() -> EchoMethod:
    """How ECHO check-ins are scored: instrument, items, thresholds and turn limits."""
    return METHOD


@router.post("/{crew_id}/sessions", status_code=status.HTTP_201_CREATED)
async def start_session(crew_id: str, c: ContainerDep) -> StartEchoResponse:
    """Open today's check-in chat; returns ECHO's opening message. 503 when no Gemini key is configured."""
    return await c.echo.start(crew_id)


@router.post("/{crew_id}/sessions/{session_id}/messages")
async def send_message(crew_id: str, session_id: str, body: EchoMessageIn, c: ContainerDep) -> EchoTurnResponse:
    """Send what the astronaut said; returns ECHO's reply."""
    return await c.echo.send(crew_id, session_id, body.content)


@router.post("/{crew_id}/sessions/{session_id}/complete")
async def complete_session(crew_id: str, session_id: str, c: ContainerDep) -> LonelinessAssessment:
    """Score the chat: loneliness score (3-9), status and advice. Idempotent."""
    return await c.echo.complete(crew_id, session_id)


@router.get("/{crew_id}/sessions/{session_id}")
async def session_detail(crew_id: str, session_id: str, c: ContainerDep) -> EchoSessionDetail:
    return await c.echo.detail(crew_id, session_id)


@router.get("/{crew_id}")
async def history(crew_id: str, c: ContainerDep) -> EchoHistory:
    """Every scored ECHO check-in for this astronaut, oldest first."""
    return c.echo.history(crew_id)

from fastapi import APIRouter, status

from app.api.deps import ContainerDep
from app.schemas.actions import ActionLogEntry, CrewMessage, RecordActionBody, ReopenBody, ResolveBody, SendMessageBody
from app.schemas.assessment import Resolution

router = APIRouter(prefix="/api", tags=["actions"])


@router.get("/actions")
async def log(c: ContainerDep) -> list[ActionLogEntry]:
    """Every logged action, oldest first."""
    return c.actions.log()


@router.post("/actions", status_code=status.HTTP_201_CREATED)
async def record(body: RecordActionBody, c: ContainerDep) -> ActionLogEntry:
    return await c.actions.record(body)


@router.get("/crew/{crew_id}/messages")
async def messages(crew_id: str, c: ContainerDep) -> list[CrewMessage]:
    """Includes messages still in transit (`deliverAt` in the future)."""
    return c.actions.messages(crew_id)


@router.post("/crew/{crew_id}/messages", status_code=status.HTTP_201_CREATED)
async def send_message(crew_id: str, body: SendMessageBody, c: ContainerDep) -> CrewMessage:
    return await c.actions.send_message(crew_id, body.text, body.insight_id)


@router.post("/insights/{insight_id}/resolve")
async def resolve(insight_id: str, body: ResolveBody, c: ContainerDep) -> Resolution:
    return await c.actions.resolve(insight_id, body.crew_id, body.note, body.severity)


@router.post("/insights/{insight_id}/reopen")
async def reopen(insight_id: str, body: ReopenBody, c: ContainerDep) -> dict[str, bool]:
    await c.actions.reopen(insight_id, body.crew_id)
    return {"ok": True}

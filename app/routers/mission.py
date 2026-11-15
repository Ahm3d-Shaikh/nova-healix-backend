from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ContainerDep
from app.schemas.mission import MissionConfig, MissionEvent

router = APIRouter(prefix="/api", tags=["mission"])

Hour = Annotated[float, Query(description="Mission hour (float hours since launch)")]


@router.get("/mission")
async def mission(c: ContainerDep) -> MissionConfig:
    """Mission config; the frontend loads it once before its first render."""
    return c.mission_config()


@router.get("/mission/events")
async def events(c: ContainerDep) -> list[MissionEvent]:
    """All mission events, past and planned. Exercise sessions are in the crew timeline."""
    return c.data.events()


@router.get("/crew/{crew_id}/timeline")
async def timeline(
    crew_id: str, c: ContainerDep, start: Annotated[Hour, Query(alias="from")], end: Annotated[Hour, Query(alias="to")]
) -> list[MissionEvent]:
    """Events that affect this astronaut in [from, to], plus their exercise sessions, sorted by start."""
    return c.telemetry.timeline(crew_id, start, end)

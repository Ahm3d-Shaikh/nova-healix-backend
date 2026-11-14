from fastapi import APIRouter

from app.api.deps import ContainerDep
from app.models.settings import MissionSettingsResponse

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.post("/reset", summary="Reset the demo to its starting state")
async def reset_demo(c: ContainerDep) -> MissionSettingsResponse:
    """Back to day 5 / Mars / live mode and forget submitted Mirror Gap and isolation check-ins,
    so every judging run starts identically (NFR-03)."""
    c.mirror_gap.clear()
    c.isolation.clear()
    settings = c.mission_settings.reset()
    return MissionSettingsResponse.build(settings, c.settings.mission_days)

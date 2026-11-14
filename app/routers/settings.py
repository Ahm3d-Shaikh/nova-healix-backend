from fastapi import APIRouter

from app.api.deps import ContainerDep
from app.models.settings import MissionSettings, MissionSettingsResponse

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def get_settings(c: ContainerDep) -> MissionSettingsResponse:
    return MissionSettingsResponse.build(c.mission_settings.get(), c.settings.mission_days)


@router.post("")
async def update_settings(body: MissionSettings, c: ContainerDep) -> MissionSettingsResponse:
    updated = c.mission_settings.update(body)
    return MissionSettingsResponse.build(updated, c.settings.mission_days)

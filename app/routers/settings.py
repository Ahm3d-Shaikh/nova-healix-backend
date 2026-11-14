from fastapi import APIRouter, Depends

from app.api.deps import get_container
from app.container import Container
from app.models.settings import MissionSettings, MissionSettingsResponse

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=MissionSettingsResponse)
async def get_settings(c: Container = Depends(get_container)):
    return MissionSettingsResponse.build(c.mission_settings.get(), c.settings.mission_days)


@router.post("", response_model=MissionSettingsResponse)
async def update_settings(body: MissionSettings, c: Container = Depends(get_container)):
    updated = c.mission_settings.update(body)
    return MissionSettingsResponse.build(updated, c.settings.mission_days)

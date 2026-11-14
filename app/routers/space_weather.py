from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ContainerDep
from app.models.space_weather import MissionEvent, SpaceWeatherResponse

router = APIRouter(prefix="/api/space-weather", tags=["space weather"])


@router.get("", summary="Normalized NASA DONKI events")
async def space_weather(
    c: ContainerDep,
    deep_space_mode: Annotated[bool | None, Query(description="Override the saved setting")] = None,
) -> SpaceWeatherResponse:
    """Live DONKI data (cached 1 h), falling back to a cache copy, then the bundled snapshot."""
    deep = c.mission_settings.get().deep_space_mode if deep_space_mode is None else deep_space_mode
    data = await c.weather.get(deep)
    start, end = c.weather.window
    return SpaceWeatherResponse(
        source=data.source,
        data_as_of=data.data_as_of,
        reason=data.reason,
        window_start=start,
        window_end=end,
        events=[MissionEvent(**e.model_dump(), mission_day=c.timeline.day_of(e.time)) for e in data.events],
    )

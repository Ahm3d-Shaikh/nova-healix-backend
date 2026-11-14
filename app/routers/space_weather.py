from fastapi import APIRouter, Depends, Query

from app.api.deps import get_container
from app.container import Container
from app.models.space_weather import MissionEvent, SpaceWeatherResponse

router = APIRouter(prefix="/api/space-weather", tags=["space weather"])


@router.get("", response_model=SpaceWeatherResponse, summary="Normalized NASA DONKI events")
async def space_weather(
    deep_space_mode: bool | None = Query(None, description="Override the saved setting"),
    c: Container = Depends(get_container),
):
    """Live DONKI data (cached 1 h), falling back to a cache copy, then the bundled snapshot."""
    deep = c.mission_settings.get().deep_space_mode if deep_space_mode is None else deep_space_mode
    data = await c.weather.get(deep)
    start, end = c.weather.window
    return SpaceWeatherResponse(
        source=data.source, data_as_of=data.data_as_of, reason=data.reason,
        window_start=start, window_end=end,
        events=[MissionEvent(**e.model_dump(), mission_day=c.timeline.day_of(e.time)) for e in data.events],
    )

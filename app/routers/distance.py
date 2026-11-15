from fastapi import APIRouter

from app.api.deps import RidgeDep
from app.models.distance import DistanceResponse

router = APIRouter(prefix="/api", tags=["distance"])


@router.get("/distance", summary="Earth distance and signal delay per mission day (JPL Horizons)")
async def distance(c: RidgeDep) -> DistanceResponse:
    """Distance to the mission destination (ISS / Moon / Mars) and one-way light time for every mission day."""
    return await c.crew.distance_series()

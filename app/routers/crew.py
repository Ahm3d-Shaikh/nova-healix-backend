from fastapi import APIRouter

from app.api.deps import ContainerDep
from app.core.errors import UnknownAstronautError
from app.schemas.crew import Astronaut

router = APIRouter(prefix="/api/crew", tags=["crew"])


@router.get("")
async def list_crew(c: ContainerDep) -> list[Astronaut]:
    """The 4 crew in display order."""
    return c.data.crew()


@router.get("/{crew_id}")
async def get_crew(crew_id: str, c: ContainerDep) -> Astronaut:
    astro = c.data.astronaut(crew_id)
    if astro is None:
        raise UnknownAstronautError(crew_id)
    return astro

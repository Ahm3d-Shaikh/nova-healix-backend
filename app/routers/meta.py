from fastapi import APIRouter

from app.api.deps import ContainerDep
from app.core.reference import DATA_PROVENANCE, DISCLAIMER, SOURCES
from app.models.meta import MetaResponse
from app.rules.registry import THRESHOLD_REGISTRY

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/meta", summary="Disclaimer, real-vs-simulated data, every threshold's provenance, sources")
async def meta(c: ContainerDep) -> MetaResponse:
    """Everything the UI needs for the on-screen disclaimer and the 'where does this number come from' view."""
    return MetaResponse(
        project="RIDGE Monitor",
        version=c.settings.app_version,
        disclaimer=DISCLAIMER,
        data=list(DATA_PROVENANCE),
        thresholds=list(THRESHOLD_REGISTRY),
        sources=list(SOURCES),
    )

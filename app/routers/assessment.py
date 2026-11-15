from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ContainerDep
from app.schemas.assessment import HazardAssessment, Insight, MetricInterpretation
from app.schemas.crew import CrewSummary
from app.schemas.telemetry import Sample

router = APIRouter(prefix="/api", tags=["assessment"])

At = Annotated[float | None, Query(description="Mission hour to evaluate (default now; never later than now)")]
Autonomous = Annotated[bool, Query(description="true while the Earth link is lost in the simulation")]


@router.get("/assessment/hazards")
async def hazards(c: ContainerDep, at: At = None, autonomous: Autonomous = False) -> list[HazardAssessment]:
    """5 rows per astronaut (one per NASA hazard, canonical order), for the whole crew."""
    return c.analysis.hazards(at, autonomous)


@router.get("/assessment/hazards/{hazard}/history")
async def hazard_history(
    hazard: str,
    crew: Annotated[str, Query(description="Astronaut id")],
    c: ContainerDep,
    from_day: Annotated[int, Query(alias="fromDay", ge=1)] = 1,
    at: At = None,
    autonomous: Autonomous = False,
) -> list[Sample]:
    """That hazard's score for one astronaut, once per day from `fromDay` to today."""
    return c.analysis.hazard_history(hazard, crew, from_day, at, autonomous)


@router.get("/assessment/crew-summaries")
async def crew_summaries(c: ContainerDep, at: At = None, autonomous: Autonomous = False) -> list[CrewSummary]:
    return c.analysis.crew_summaries(at, autonomous)


@router.get("/insights")
async def insights(c: ContainerDep, at: At = None, autonomous: Autonomous = False) -> list[Insight]:
    """Every finding for the whole crew, including resolved ones; safety alerts first."""
    return c.analysis.insights(at, autonomous)


@router.get("/crew/{crew_id}/metrics/{metric}/interpretation")
async def interpretation(
    crew_id: str, metric: str, c: ContainerDep, at: At = None, autonomous: Autonomous = False
) -> MetricInterpretation:
    return c.analysis.interpret(crew_id, metric, at, autonomous)

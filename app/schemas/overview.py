"""Convenience views that combine the core data: distance, a one-call dashboard and the active alerts."""

from datetime import datetime

from app.schemas.assessment import HazardAssessment, Insight
from app.schemas.base import CamelModel
from app.schemas.crew import Astronaut, CrewSummary
from app.schemas.mission import MissionEvent


class DistancePoint(CamelModel):
    day: int
    distance_km: float
    light_time_s: float  # one-way


class DistanceResponse(CamelModel):
    mission: str
    target: str
    source: str  # "NASA JPL Horizons" when the arrival distance is real NASA data, else "model"
    as_of: datetime | None
    duration_days: int
    days: list[DistancePoint]


class Link(CamelModel):
    mode: str  # "nominal" | "autonomous"
    delay_seconds: float  # one-way light time to Earth
    distance_au: float


class DashboardCrew(CamelModel):
    astronaut: Astronaut
    summary: CrewSummary
    hazards: list[HazardAssessment]  # 5, canonical order
    insights: list[Insight]  # active (unresolved) findings for this astronaut


class Dashboard(CamelModel):
    disclaimer: str
    mission_hour: float
    day: int
    duration_days: int
    link: Link
    recent_space_events: list[MissionEvent]  # real NASA DONKI events in the last 24 h
    crew: list[DashboardCrew]
    crew_wide_insights: list[Insight]  # active findings that concern the whole crew

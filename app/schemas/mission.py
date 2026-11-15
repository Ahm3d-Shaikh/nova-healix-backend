from typing import Literal

from app.schemas.base import CamelModel

HazardKey = Literal["radiation", "isolation", "distance", "gravity", "environment"]
HAZARD_KEYS: tuple[HazardKey, ...] = ("radiation", "isolation", "distance", "gravity", "environment")
MissionEventKind = Literal["eva", "spe", "exercise", "sleep-shift", "burn", "medical", "anomaly"]


class Team(CamelModel):
    flight_surgeon: str
    flight_director: str


class MissionConfig(CamelModel):
    code: str
    name: str
    vehicle: str
    duration_days: int
    launch_epoch_ms: int
    career_dose_limit_msv: float
    current_day: int
    trajectory_au: list[float]
    team: Team


class MissionEvent(CamelModel):
    omit_when_none = frozenset({"planned", "missed"})

    id: str
    kind: MissionEventKind
    label: str
    start: float
    end: float
    crew_ids: list[str]
    hazards: list[HazardKey]
    planned: bool | None = None
    missed: bool | None = None

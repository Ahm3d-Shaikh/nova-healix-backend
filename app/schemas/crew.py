from typing import Literal

from app.schemas.base import CamelModel

CrewRole = Literal["CDR", "FE", "MS", "CMO"]
Status = Literal["nominal", "watch", "alert"]


class Astronaut(CamelModel):
    id: str
    name: str
    role: CrewRole
    callsign: str
    age: int
    agency: str
    sleep_start_hour: float
    exercise_hour: float
    persona: str


class NextEvent(CamelModel):
    label: str
    day: int


class CrewSummary(CamelModel):
    crew_id: str
    status: Status
    check_in_hour: float | None
    next_event: NextEvent | None

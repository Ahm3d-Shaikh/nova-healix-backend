from pydantic import BaseModel

from app.models.enums import Hazard, Level


class Alert(BaseModel):
    """Result of one rule. Green results mean 'checked, nothing to flag'."""

    rule: str
    hazard: Hazard
    level: Level
    what: str
    why: str
    action: str
    source: str


class CrewAlert(Alert):
    astronaut_id: str
    astronaut_name: str
    day: int

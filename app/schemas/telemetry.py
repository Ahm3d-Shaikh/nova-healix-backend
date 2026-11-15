from typing import Literal

from pydantic import Field

from app.schemas.base import CamelModel

Symptom = Literal["headache", "nausea", "vision", "back-pain", "congestion", "other"]


class Sample(CamelModel):
    t: float
    v: float


class Baseline(CamelModel):
    mean: float
    low: float
    high: float
    source: str


class LiveVitals(CamelModel):
    crew_id: str
    t: float
    values: dict[str, float]


class CheckInDraft(CamelModel):
    omit_when_none = frozenset({"note"})

    mood: int = Field(ge=1, le=5)
    sleep_quality: int = Field(ge=1, le=5)
    energy: int = Field(ge=1, le=5)
    symptoms: list[Symptom] = Field(default_factory=list)
    note: str | None = Field(default=None, max_length=2000)


class CheckIn(CamelModel):
    omit_when_none = frozenset({"note"})

    id: str
    crew_id: str
    day: int
    at: float
    mood: int
    sleep_quality: int
    energy: int
    symptoms: list[Symptom]
    note: str | None = None

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.alert import Alert
from app.models.enums import Level


class QuestionOption(BaseModel):
    value: int
    label: str


class Question(BaseModel):
    id: str
    text: str


class Questionnaire(BaseModel):
    name: str
    source: str
    questions: list[Question]
    options: list[QuestionOption]
    score_range: tuple[int, int]
    bands: dict[str, str]


class IsolationSubmission(BaseModel):
    q1: int = Field(ge=1, le=3, description="Lack companionship")
    q2: int = Field(ge=1, le=3, description="Left out")
    q3: int = Field(ge=1, le=3, description="Isolated from others")


class IsolationResult(BaseModel):
    answers: list[int]
    score: int
    level: Level
    consecutive_days_at_or_above_7: int
    alert: Alert
    created_at: datetime


class IsolationHistoryItem(BaseModel):
    day: int | None
    source: str  # "simulated" | "submitted"
    score: int


class IsolationHistory(BaseModel):
    astronaut_id: str
    items: list[IsolationHistoryItem]

from typing import Literal

from pydantic import Field

from app.schemas.base import CamelModel
from app.schemas.mission import HazardKey

QuestionnaireId = Literal["wellbeing", "sleep", "workload", "team"]
AnswerValue = int | float | str


class QuestionOption(CamelModel):
    value: int
    label: str


class Question(CamelModel):
    omit_when_none = frozenset({"options", "reverse", "optional"})

    id: str
    text: str
    kind: Literal["scale", "text"]
    options: list[QuestionOption] | None = None
    reverse: bool | None = None
    optional: bool | None = None


class Questionnaire(CamelModel):
    omit_when_none = frozenset({"feeds"})

    id: QuestionnaireId
    title: str
    purpose: str
    minutes: int
    hazards: list[HazardKey]
    feeds: str | None = None
    score_meaning: str
    questions: list[Question]


class Assignment(CamelModel):
    omit_when_none = frozenset({"note", "completed_at", "score"})

    id: str
    crew_id: str
    questionnaire_id: QuestionnaireId
    assigned_by: str
    note: str | None = None
    assigned_at: float
    due_day: int
    status: Literal["assigned", "in-progress", "done"]
    answers: dict[str, AnswerValue]
    current_index: int
    completed_at: float | None = None
    score: int | None = None


class ProgressBody(CamelModel):
    answers: dict[str, AnswerValue] = Field(default_factory=dict)
    current_index: int = Field(ge=0, default=0)


class SubmitBody(CamelModel):
    answers: dict[str, AnswerValue] = Field(default_factory=dict)

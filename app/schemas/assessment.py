from typing import Literal

from app.schemas.base import CamelModel
from app.schemas.crew import Status
from app.schemas.mission import HazardKey

Severity = Literal["alert", "watch", "info"]
Direction = Literal["up", "down", "flat"]
ActionKind = Literal["acknowledge", "message", "questionnaire", "countermeasure", "escalate"]
LogKind = Literal[
    "acknowledge",
    "message",
    "in-person",
    "psych",
    "medical",
    "escalate",
    "countermeasure",
    "questionnaire",
    "resolve",
    "reopen",
]
Countermeasure = Literal["exercise", "sleep-shift", "rest", "storm-shelter"]


class HazardDriver(CamelModel):
    omit_when_none = frozenset({"metric", "concern"})

    label: str
    value: str
    contribution: int
    metric: str | None = None
    concern: str | None = None


class HazardAssessment(CamelModel):
    crew_id: str
    hazard: HazardKey
    score: int
    status: Status
    drivers: list[HazardDriver]
    headline: str
    explanation: str


class Evidence(CamelModel):
    omit_when_none = frozenset({"reference", "metric", "crew_id", "direction"})

    label: str
    value: str
    reference: str | None = None
    metric: str | None = None
    crew_id: str | None = None
    direction: Direction | None = None


class RecommendedAction(CamelModel):
    omit_when_none = frozenset({"countermeasure", "questionnaire_id", "log"})

    kind: ActionKind
    label: str
    detail: str
    countermeasure: Countermeasure | None = None
    questionnaire_id: str | None = None
    log: LogKind | None = None


class Resolution(CamelModel):
    at: float
    by: str
    note: str
    severity: Severity


class Insight(CamelModel):
    omit_when_none = frozenset({"primary_metric", "resolution", "reopened"})

    id: str
    crew_id: str | None
    severity: Severity
    hazards: list[HazardKey]
    title: str
    summary: str
    why_it_matters: str
    detected_at: float
    primary_metric: str | None = None
    evidence: list[Evidence]
    confidence: float
    recommended: list[RecommendedAction]
    resolution: Resolution | None = None
    reopened: bool | None = None


class MetricInterpretation(CamelModel):
    crew_id: str
    metric: str
    summary: str
    why_it_matters: str
    contributing: list[Evidence]
    confidence: float
    recommended: list[RecommendedAction]
    trend: Direction
    status: Status

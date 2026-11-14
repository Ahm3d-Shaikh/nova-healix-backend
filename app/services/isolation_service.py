"""Three-Item Loneliness Scale check-ins (in memory)."""

from datetime import UTC, datetime

from app.models.isolation import (
    IsolationHistory,
    IsolationHistoryItem,
    IsolationResult,
    IsolationSubmission,
    Question,
    Questionnaire,
    QuestionOption,
)
from app.rules import isolation as rule
from app.rules import thresholds as t
from app.services.crew_service import CrewService
from app.services.store import InMemoryStore

QUESTIONNAIRE = Questionnaire(
    name="Three-Item Loneliness Scale",
    source="Hughes et al., 2004",
    questions=[Question(id=f"q{i}", text=text) for i, text in enumerate(rule.QUESTIONS, start=1)],
    options=[
        QuestionOption(value=1, label="Hardly ever"),
        QuestionOption(value=2, label="Some of the time"),
        QuestionOption(value=3, label="Often"),
    ],
    score_range=(t.LONELINESS_MIN, t.LONELINESS_MAX),
    bands={"3-5": "green", "6-9": "amber", ">=7 for 3 consecutive days": "red (our rule, illustrative)"},
)


class IsolationService:
    def __init__(self, crew: CrewService) -> None:
        self._crew = crew
        self._submitted: InMemoryStore[IsolationResult] = InMemoryStore()

    def submit(self, astronaut_id: str, body: IsolationSubmission, day: int) -> IsolationResult:
        """Score a check-in for mission `day`; the streak rule uses the days before it."""
        astro = self._crew.astronaut(astronaut_id)
        score = body.q1 + body.q2 + body.q3
        prior = [r.loneliness_total for r in self._crew.records(astro.id)[: max(0, day - 1)]]
        prior += [s.score for s in self._submitted.all(astro.id)]
        series = [*prior, score]
        alert = rule.assess(series)
        result = IsolationResult(
            answers=[body.q1, body.q2, body.q3],
            score=score,
            level=alert.level,
            consecutive_days_at_or_above_7=rule.high_streak(series),
            alert=alert,
            created_at=datetime.now(UTC),
        )
        self._submitted.add(astro.id, result)
        return result

    def history(self, astronaut_id: str) -> IsolationHistory:
        astro = self._crew.astronaut(astronaut_id)
        items = [
            IsolationHistoryItem(day=r.day, source="simulated", score=r.loneliness_total)
            for r in self._crew.records(astro.id)
        ]
        items += [
            IsolationHistoryItem(day=None, source="submitted", score=s.score) for s in self._submitted.all(astro.id)
        ]
        return IsolationHistory(astronaut_id=astro.id, items=items)

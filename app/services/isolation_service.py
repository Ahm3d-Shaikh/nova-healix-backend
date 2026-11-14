"""Three-Item Loneliness Scale check-ins (in memory)."""

from datetime import datetime, timezone

from app.models.enums import Level
from app.models.isolation import (
    IsolationHistory, IsolationHistoryItem, IsolationResult, IsolationSubmission,
    Question, QuestionOption, Questionnaire,
)
from app.rules import isolation as rule
from app.rules.stats import trailing_streak
from app.services.crew_service import CrewService

QUESTIONNAIRE = Questionnaire(
    name="Three-Item Loneliness Scale",
    source="Hughes et al., 2004",
    questions=[Question(id=f"q{i}", text=t) for i, t in enumerate(rule.QUESTIONS, start=1)],
    options=[QuestionOption(value=1, label="Hardly ever"), QuestionOption(value=2, label="Some of the time"),
             QuestionOption(value=3, label="Often")],
    score_range=(3, 9),
    bands={"3-5": "green", "6-9": "amber", ">=7 for 3 consecutive days": "red (our rule, illustrative)"},
)


class IsolationService:
    def __init__(self, crew: CrewService):
        self._crew = crew
        self._submitted: dict[str, list[IsolationResult]] = {}

    def _prior_scores(self, astronaut_id: str) -> list[int]:
        day = self._crew.resolve_day(None)
        sim = self._crew.records(astronaut_id)[: max(0, day - 1)]
        return [r.loneliness_total for r in sim] + [s.score for s in self._submitted.get(astronaut_id, [])]

    def submit(self, astronaut_id: str, body: IsolationSubmission) -> IsolationResult:
        astro = self._crew.astronaut(astronaut_id)
        score = body.q1 + body.q2 + body.q3
        series = [*self._prior_scores(astro.id), score]
        alert = rule.assess(series)
        result = IsolationResult(
            answers=[body.q1, body.q2, body.q3], score=score, level=alert.level,
            consecutive_days_at_or_above_7=trailing_streak([t >= 7 for t in series]),
            alert=alert, created_at=datetime.now(timezone.utc),
        )
        self._submitted.setdefault(astro.id, []).append(result)
        return result

    def history(self, astronaut_id: str) -> IsolationHistory:
        astro = self._crew.astronaut(astronaut_id)
        items = [IsolationHistoryItem(day=r.day, source="simulated", score=r.loneliness_total)
                 for r in self._crew.records(astro.id)]
        items += [IsolationHistoryItem(day=None, source="submitted", score=s.score)
                  for s in self._submitted.get(astro.id, [])]
        return IsolationHistory(astronaut_id=astro.id, items=items)

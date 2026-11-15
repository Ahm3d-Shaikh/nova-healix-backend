"""Crew Mode: daily check-ins and questionnaire assignments (data shared with Mission Control)."""

from app.core.errors import AlreadySubmittedError, InvalidAnswersError, UnknownAssignmentError, UnknownAstronautError
from app.domain.mission_plan import hour_to_day
from app.domain.questionnaires import QUESTIONNAIRES, score_questionnaire
from app.domain.store import MissionData
from app.repositories.state import StateRepository
from app.schemas.crewmode import AnswerValue, Assignment, Questionnaire
from app.schemas.telemetry import CheckIn, CheckInDraft
from app.services.clock import MissionClock


class CrewModeService:
    def __init__(self, data: MissionData, clock: MissionClock, repo: StateRepository) -> None:
        self._data = data
        self._clock = clock
        self._repo = repo

    def _crew(self, crew_id: str) -> str:
        if self._data.astronaut(crew_id) is None:
            raise UnknownAstronautError(crew_id)
        return crew_id

    async def submit_check_in(self, crew_id: str, draft: CheckInDraft) -> CheckIn:
        """One check-in per astronaut per day: a second one on the same day replaces the first."""
        self._crew(crew_id)
        t = self._clock.quarter_hour()
        day = hour_to_day(t)
        note = draft.note.strip() if draft.note else None
        check_in = CheckIn(
            id=f"ci-{crew_id}-{day}",
            crew_id=crew_id,
            day=day,
            at=t,
            mood=draft.mood,
            sleep_quality=draft.sleep_quality,
            energy=draft.energy,
            symptoms=draft.symptoms,
            note=note or None,
        )
        await self._repo.save_check_in(check_in)
        self._data.add_check_in(check_in)
        return check_in

    @staticmethod
    def questionnaires() -> dict[str, Questionnaire]:
        return QUESTIONNAIRES

    def assignments(self, crew_id: str) -> list[Assignment]:
        self._crew(crew_id)
        return self._data.assignments(crew_id)

    def assignment(self, assignment_id: str) -> Assignment:
        a = next((x for x in self._data.assignments() if x.id == assignment_id), None)
        if a is None:
            raise UnknownAssignmentError(assignment_id)
        return a

    async def save_progress(
        self, assignment_id: str, answers: dict[str, AnswerValue], current_index: int
    ) -> Assignment:
        a = self.assignment(assignment_id)
        self._validate_answers(a, answers)
        updated = a.model_copy(
            update={
                "answers": answers,
                "current_index": current_index,
                "status": "done" if a.status == "done" else "in-progress",
            }
        )
        await self._repo.save_assignment(updated)
        self._data.upsert_assignment(updated)
        return updated

    async def submit(self, assignment_id: str, answers: dict[str, AnswerValue]) -> Assignment:
        a = self.assignment(assignment_id)
        if a.status == "done":
            raise AlreadySubmittedError
        self._validate_answers(a, answers)
        q = QUESTIONNAIRES[a.questionnaire_id]
        t = self._clock.quarter_hour()
        score = score_questionnaire(q, answers)
        done = a.model_copy(
            update={
                "answers": answers,
                "status": "done",
                "completed_at": t,
                "score": score,
                "current_index": len(q.questions),
            }
        )
        if q.feeds:  # the score becomes a sample of this metric, so Mission Control sees the result
            await self._repo.save_sample(a.crew_id, q.feeds, t, score)
        await self._repo.save_assignment(done)
        if q.feeds:
            self._data.add_sample(a.crew_id, q.feeds, t, float(score))
        self._data.upsert_assignment(done)
        return done

    @staticmethod
    def _validate_answers(a: Assignment, answers: dict[str, AnswerValue]) -> None:
        q = QUESTIONNAIRES[a.questionnaire_id]
        by_id = {x.id: x for x in q.questions}
        for qid, value in answers.items():
            question = by_id.get(qid)
            if question is None:
                raise InvalidAnswersError(f"Unknown question '{qid}'")
            if question.kind == "scale" and (
                isinstance(value, bool) or not isinstance(value, int | float) or not 1 <= value <= 5
            ):
                raise InvalidAnswersError(f"Answer to '{qid}' must be a number from 1 to 5")
            if question.kind == "text" and (not isinstance(value, str) or len(value) > 2000):
                raise InvalidAnswersError(f"Answer to '{qid}' must be text of at most 2000 characters")

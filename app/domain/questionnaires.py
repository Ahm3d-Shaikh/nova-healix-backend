"""Questionnaires (frontend `questionnaires.ts`, exported to JSON) and scoring."""

import json

from app.domain.metrics import DATA_DIR
from app.domain.prng import js_round
from app.schemas.crewmode import AnswerValue, Assignment, Questionnaire, QuestionnaireId

QUESTIONNAIRES: dict[str, Questionnaire] = {
    qid: Questionnaire.model_validate(q) for qid, q in json.loads((DATA_DIR / "questionnaires.json").read_text()).items()
}


def questionnaire(qid: QuestionnaireId | str) -> Questionnaire:
    return QUESTIONNAIRES[qid]


def score_questionnaire(q: Questionnaire, answers: dict[str, AnswerValue]) -> int:
    """0-100, higher = more strain. Text answers are ignored; `reverse` items count as 6 - answer."""
    vals: list[float] = []
    for question in q.questions:
        if question.kind != "scale":
            continue
        a = answers.get(question.id)
        if isinstance(a, bool) or not isinstance(a, int | float):
            continue
        vals.append(6 - a if question.reverse else a)
    if not vals:
        return 0
    mean = sum(vals) / len(vals)
    return int(js_round(((mean - 1) / 4) * 100))


def seed_assignments() -> list[Assignment]:
    """Assignments already on board at Day 142 (assigned by the flight surgeon)."""
    return [Assignment.model_validate(a) for a in json.loads((DATA_DIR / "seed_assignments.json").read_text())]

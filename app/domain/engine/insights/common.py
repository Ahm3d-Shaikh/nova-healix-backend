"""Shared pieces of the insight rules: labels, severity order and small helpers."""

from collections.abc import Callable

from app.domain.engine.context import EngineContext
from app.domain.prng import clamp, js_round
from app.schemas.assessment import Evidence, Insight

SEVERITY_RANK = {"info": 0, "watch": 1, "alert": 2}
SYMPTOM_LABEL = {
    "headache": "Headache",
    "nausea": "Nausea",
    "vision": "Vision change",
    "back-pain": "Back pain",
    "congestion": "Congestion",
    "other": "Other",
}
SAFETY_SIGNAL_LABEL = {
    "wish-to-die": "expressed a wish to die",
    "suicidal-thoughts": "expressed suicidal thoughts",
    "self-harm-intent": "expressed intent to harm themself",
    "confirmed-when-asked": "said yes when Nova asked about thoughts of self-harm",
    "chest-pain": "reported chest pain",
    "breathing": "reported difficulty breathing",
    "stroke-signs": "reported stroke-like symptoms (numbness or slurred speech)",
    "unconscious": "reported fainting or blacking out",
    "vision-loss": "reported sudden loss of vision",
    "severe-headache": "reported a sudden severe headache",
    "seizure": "reported a seizure",
}

Rule = Callable[[EngineContext, str], Insight | None]


def confidence(signals: int, base: float = 0.56) -> float:
    return js_round(clamp(base + signals * 0.08, 0, 0.95) * 100) / 100


def display_name(ctx: EngineContext, crew_id: str) -> str:
    a = ctx.db.astronaut(crew_id)
    return a.name if a else crew_id


def direction_of(now: float, ref: float) -> str:
    return "flat" if abs(now - ref) < 1e-6 else ("up" if now > ref else "down")


def make_evidence(label: str, value: str, **kw: object) -> Evidence:
    return Evidence(label=label, value=value, **kw)


def first_word(label: str) -> str:
    return label.split(" ", maxsplit=1)[0]

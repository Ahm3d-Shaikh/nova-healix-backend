"""Simulated crew personas and planted storylines (frontend `personas.ts`, exported to JSON)."""

import json
from dataclasses import dataclass, field
from typing import Any

from app.domain.metrics import DATA_DIR
from app.schemas.crew import Astronaut


@dataclass(frozen=True)
class Ramp:
    start: int  # day
    end: int
    delta: float


@dataclass(frozen=True)
class Persona:
    astronaut: Astronaut
    params: dict[str, float]
    story: dict[str, list[Ramp]]
    symptoms: dict[int, list[str]]
    notes: dict[int, str]
    missed_check_ins: frozenset[int]
    skipped_exercise: frozenset[int] = field(default_factory=frozenset)


def _load() -> dict[str, Persona]:
    raw: dict[str, Any] = json.loads((DATA_DIR / "personas.json").read_text())
    out: dict[str, Persona] = {}
    for crew_id, p in raw.items():
        out[crew_id] = Persona(
            astronaut=Astronaut.model_validate(p["astronaut"]),
            params={k: float(v) for k, v in p["params"].items()},
            story={ch: [Ramp(r["from"], r["to"], r["delta"]) for r in ramps] for ch, ramps in p["story"].items()},
            symptoms={int(d): list(s) for d, s in p["symptoms"].items()},
            notes={int(d): n for d, n in p["notes"].items()},
            missed_check_ins=frozenset(p["missedCheckIns"]),
            skipped_exercise=frozenset(p.get("skippedExercise", [])),
        )
    return out


PERSONAS: dict[str, Persona] = _load()


def story_value(p: Persona, channel: str, day: int) -> float:
    """Value of a story channel on a given day (sum of ramps)."""
    v = 0.0
    for r in p.story.get(channel, []):
        f = (1.0 if day >= r.end else 0.0) if r.end == r.start else (day - r.start) / (r.end - r.start)
        v += r.delta * min(1.0, max(0.0, f))
    return v

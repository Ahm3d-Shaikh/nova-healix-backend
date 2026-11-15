"""One-way light time to Earth from the mission trajectory (frontend `util/link.ts`)."""

import math
from dataclasses import dataclass
from typing import Literal

from app.domain.mission_plan import LIGHT_SECONDS_PER_AU


@dataclass(frozen=True)
class LinkState:
    mode: Literal["nominal", "autonomous"]
    delay_seconds: float
    distance_au: float


def link_state_at(trajectory_au: list[float], hour: float, autonomous: bool) -> LinkState:
    day_f = hour / 24
    i = max(0, min(len(trajectory_au) - 2, math.floor(day_f)))
    f = max(0.0, min(1.0, day_f - i))
    au = trajectory_au[i] * (1 - f) + trajectory_au[i + 1] * f
    return LinkState("autonomous" if autonomous else "nominal", au * LIGHT_SECONDS_PER_AU, au)

"""Mission constants and timeline (frontend `mission-plan.ts`)."""

import json
import math

from app.domain.metrics import DATA_DIR
from app.schemas.mission import MissionEvent

HOURS_PER_DAY = 24
DAY_MS = 86_400_000
HOUR_MS = 3_600_000

MISSION_DURATION_DAYS = 260
CURRENT_DAY = 142
GENERATED_DAYS = CURRENT_DAY + 4  # a few days past "today" so a session across midnight UTC stays covered
GENERATED_HOURS = GENERATED_DAYS * HOURS_PER_DAY

BASELINE_FROM_DAY = 8
BASELINE_TO_DAY = 40

CREW_IDS: tuple[str, ...] = ("hashir", "ahmad", "hannan", "sabaina")
LIGHT_SECONDS_PER_AU = 499.005
CAREER_DOSE_LIMIT_MSV = 600.0
FLIGHT_SURGEON = "Haleem"
FLIGHT_DIRECTOR = "Hamza"


def day_start_hour(day: int) -> float:
    return (day - 1) * HOURS_PER_DAY


def hour_to_day(hour: float) -> int:
    return math.floor(hour / HOURS_PER_DAY) + 1


def at(day: int, hour_of_day: float) -> float:
    return day_start_hour(day) + hour_of_day


def distance_au_on_day(day: int) -> float:
    """Earth-ship distance on an outbound Mars transit, AU (~0 at launch to ~1.45 AU at arrival)."""
    x = min(1.0, max(0.0, day / MISSION_DURATION_DAYS))
    return float(0.004 + 1.45 * x**1.3)


def default_trajectory_au() -> list[float]:
    """Fallback when JPL Horizons is unavailable: one value per day, durationDays + 1 values."""
    return [distance_au_on_day(i + 1) for i in range(MISSION_DURATION_DAYS + 1)]


def _load_events() -> list[MissionEvent]:
    raw = json.loads((DATA_DIR / "mission_events.json").read_text())
    return [MissionEvent.model_validate(e) for e in raw]


# `end` for the open-ended anomaly is the frontend's GENERATED_HOURS (already numeric in the JSON).
MISSION_EVENTS: list[MissionEvent] = _load_events()

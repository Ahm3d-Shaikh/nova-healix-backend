from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.models.alert import Alert
from app.models.enums import Level


class TestMode(StrEnum):
    PVT_B_3MIN = "pvt_b_3min"
    DEMO_60S = "demo_60s"  # judge demo, not validated


class LapseBand(StrEnum):
    GOOD = "good"
    REDUCED = "reduced"
    POOR = "poor"


class MirrorGapSubmission(BaseModel):
    self_rating: int = Field(ge=1, le=10, description="How sharp do I feel? 1-10")
    reaction_times_ms: list[float] = Field(min_length=5, max_length=1000)
    mode: TestMode = TestMode.PVT_B_3MIN


class MirrorGapResult(BaseModel):
    mode: TestMode
    validated: bool
    self_rating: int
    responses: int
    mean_rt_ms: float
    mean_speed: float  # mean 1/RT in 1/s
    lapses: int
    false_starts: int
    lapse_band: LapseBand | None  # only for the validated 3-minute test
    z_self: float | None
    z_performance: float | None
    gap: float | None
    level: Level
    alert: Alert
    created_at: datetime


class MirrorGapHistoryItem(BaseModel):
    day: int | None  # simulated mission day, or None for a live submission
    source: str  # "simulated" | "submitted"
    self_rating: int
    mean_rt_ms: float
    lapses: int
    gap: float | None
    level: Level


class MirrorGapHistory(BaseModel):
    astronaut_id: str
    baseline_sessions: int
    items: list[MirrorGapHistoryItem]

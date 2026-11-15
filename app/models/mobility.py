"""Mobility & Balance Check: three short movement tests measured in the browser (MediaPipe Pose).

The frontend sends only the final numbers; no video ever reaches the server.
This measures movement (balance, leg strength, joint range), never bone health.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.alert import Alert
from app.models.enums import Level


class MobilityMeasurements(BaseModel):
    balance_hold_s: float = Field(ge=0, le=30, description="Single-leg stance: seconds held (stop at 30)")
    sway_pct_height: float = Field(
        ge=0, le=50, description="Single-leg stance: RMS sway of the hip centre, as % of body height"
    )
    sit_to_stand_5x_s: float = Field(gt=1, le=120, description="Seconds to complete 5 sit-to-stand repetitions")
    knee_flexion_deg: float = Field(
        ge=0, le=150, description="Deepest knee bend in a bodyweight squat, degrees (above 150 is a tracking error)"
    )
    pose_confidence: float = Field(ge=0, le=1, description="Mean MediaPipe keypoint visibility across the tests")


class MobilityCheck(BaseModel):
    """One stored check."""

    id: str
    astronaut_id: str
    mission_day: int
    created_at: datetime
    measurements: MobilityMeasurements
    reliable: bool  # pose confidence high enough to use


class TestResult(BaseModel):
    """Outcome of one test (the balance test covers both hold time and sway)."""

    test: str  # balance | sit_to_stand | squat_rom
    label: str
    level: Level
    values: dict[str, float]
    baseline: dict[str, float] | None  # same keys; the astronaut's first reliable check
    change_pct: dict[str, float] | None  # worsening vs baseline in % (positive = worse)
    note: str


class MobilityResult(BaseModel):
    level: Level
    tests: list[TestResult]
    alert: Alert
    checks_used: int
    last_check_day: int


class MobilitySubmission(BaseModel):
    check: MobilityCheck
    counted: bool  # False when pose confidence was too low (retake advised)
    result: MobilityResult | None
    message: str


class MobilityHistory(BaseModel):
    astronaut_id: str
    checks: list[MobilityCheck]
    latest: MobilityResult | None


class MobilityTestSpec(BaseModel):
    test: str
    label: str
    duration_s: int
    instructions: str
    send: list[str]


class MobilityMethod(BaseModel):
    title: str
    total_duration_s: int
    tests: list[MobilityTestSpec]
    min_pose_confidence: float
    thresholds: dict[str, float]
    limits: str


class MobilityMetrics(BaseModel):
    """Numbers shown on the Gravity card (None on the card when no check has been done)."""

    level: Level
    checks_used: int
    last_check_day: int
    tests: list[TestResult]

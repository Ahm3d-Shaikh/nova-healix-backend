"""Mobility & Balance Check: three short movement tests measured in the browser (MediaPipe Pose).

The frontend sends only the final numbers; no video ever reaches the server. This measures movement
(balance, leg strength, knee range of motion), never bone health. Additive to the guide's API: nothing
else in the contract depends on it.
"""

from pydantic import Field

from app.schemas.base import CamelModel
from app.schemas.crew import Status


class MobilityMeasurements(CamelModel):
    balance_hold_s: float = Field(ge=0, le=30, description="Single-leg stance: seconds held (stop at 30)")
    sway_pct_height: float = Field(
        ge=0, le=50, description="Single-leg stance: RMS sway of the hip centre, as % of body height"
    )
    sit_to_stand_s: float = Field(gt=1, le=120, description="Seconds to complete 5 sit-to-stand repetitions")
    knee_flexion_deg: float = Field(
        ge=0, le=150, description="Deepest knee bend in a bodyweight squat, degrees (above 150 is a tracking error)"
    )
    pose_confidence: float = Field(ge=0, le=1, description="Mean MediaPipe keypoint visibility across the tests")


class MobilityCheck(CamelModel):
    """One stored check."""

    id: str
    crew_id: str
    day: int
    at: float  # mission hour submitted
    measurements: MobilityMeasurements
    reliable: bool  # pose confidence high enough to use


class MobilityTestResult(CamelModel):
    """Outcome of one test (the balance test covers both hold time and sway)."""

    test: str  # balance | sit_to_stand | squat_rom
    label: str
    status: Status
    values: dict[str, float]
    baseline: dict[str, float] | None  # same keys; the astronaut's first reliable check
    change_pct: dict[str, float] | None  # % worse than baseline (positive = worse)
    note: str


class MobilityResult(CamelModel):
    status: Status
    tests: list[MobilityTestResult]
    checks_used: int
    last_check_at: float
    last_check_day: int


class MobilitySubmission(CamelModel):
    check: MobilityCheck
    counted: bool  # False when pose confidence was too low (retake advised)
    result: MobilityResult | None
    message: str


class MobilityHistory(CamelModel):
    crew_id: str
    checks: list[MobilityCheck]
    latest: MobilityResult | None


class MobilityTestSpec(CamelModel):
    test: str
    label: str
    duration_s: int
    instructions: str
    send: list[str]


class MobilityMethod(CamelModel):
    title: str
    total_duration_s: int
    tests: list[MobilityTestSpec]
    min_pose_confidence: float
    thresholds: dict[str, float]
    limits: str

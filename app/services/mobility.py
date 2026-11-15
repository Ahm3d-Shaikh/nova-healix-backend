"""Mobility & Balance Check: store a check measured in the browser and score it."""

import uuid

from app.core.errors import UnknownAstronautError
from app.domain import mobility
from app.domain.mission_plan import hour_to_day
from app.domain.store import MissionData
from app.repositories.state import StateRepository
from app.schemas.mobility import (
    MobilityCheck,
    MobilityHistory,
    MobilityMeasurements,
    MobilityMethod,
    MobilitySubmission,
    MobilityTestSpec,
)
from app.services.clock import MissionClock

METHOD = MobilityMethod(
    title="Mobility & Balance Check",
    total_duration_s=120,
    tests=[
        MobilityTestSpec(
            test="balance",
            label="Single-leg balance",
            duration_s=30,
            instructions="Stand on one leg, hands on hips, eyes open. Hold up to 30 seconds.",
            send=["balanceHoldS", "swayPctHeight"],
        ),
        MobilityTestSpec(
            test="sit_to_stand",
            label="5x sit-to-stand",
            duration_s=30,
            instructions="Arms crossed, stand up fully and sit down 5 times as fast as is safe.",
            send=["sitToStandS"],
        ),
        MobilityTestSpec(
            test="squat_rom",
            label="Squat knee bend",
            duration_s=20,
            instructions="Side-on to the camera, do 3 slow bodyweight squats as deep as is comfortable.",
            send=["kneeFlexionDeg"],
        ),
    ],
    min_pose_confidence=mobility.MIN_CONFIDENCE,
    thresholds={
        "balanceHoldWatchS": mobility.BALANCE_HOLD_WATCH_S,
        "balanceHoldAlertS": mobility.BALANCE_HOLD_ALERT_S,
        "sitToStandWatchS": mobility.SIT_STAND_WATCH_S,
        "sitToStandAlertS": mobility.SIT_STAND_ALERT_S,
        "kneeFlexionWatchDeg": mobility.KNEE_FLEXION_WATCH_DEG,
        "kneeFlexionAlertDeg": mobility.KNEE_FLEXION_ALERT_DEG,
        "worseThanFirstCheckWatch": mobility.CHANGE_WATCH,
        "worseThanFirstCheckAlert": mobility.CHANGE_ALERT,
    },
    limits=(
        "Measures movement (balance, leg strength, knee range of motion) from body keypoints. "
        "It cannot assess bone health or bone loss, which needs a bone density scan. "
        "Video stays on the device; only these numbers are sent. Thresholds are illustrative, not clinical."
    ),
)


class MobilityService:
    def __init__(self, data: MissionData, clock: MissionClock, repo: StateRepository) -> None:
        self._data = data
        self._clock = clock
        self._repo = repo

    def _crew(self, crew_id: str) -> str:
        if self._data.astronaut(crew_id) is None:
            raise UnknownAstronautError(crew_id)
        return crew_id

    async def submit(self, crew_id: str, m: MobilityMeasurements) -> MobilitySubmission:
        self._crew(crew_id)
        at = self._clock.now_hour()
        check = MobilityCheck(
            id=f"mob-{crew_id}-{uuid.uuid4().hex[:8]}",
            crew_id=crew_id,
            day=hour_to_day(at),
            at=at,
            measurements=m,
            reliable=m.pose_confidence >= mobility.MIN_CONFIDENCE,
        )
        await self._repo.save_mobility_check(check)
        self._data.add_mobility_check(check)
        result = mobility.assess(self._data.mobility_checks(crew_id))
        message = (
            "Check saved."
            if check.reliable
            else "Pose tracking was not clear enough to use this check. Retake it in good light, full body in view."
        )
        return MobilitySubmission(check=check, counted=check.reliable, result=result, message=message)

    def history(self, crew_id: str) -> MobilityHistory:
        self._crew(crew_id)
        checks = self._data.mobility_checks(crew_id)
        return MobilityHistory(crew_id=crew_id, checks=checks, latest=mobility.assess(checks))

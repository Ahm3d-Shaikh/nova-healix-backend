"""Mobility & Balance Check: store a check and score it with the Gravity rules."""

from app.models.mobility import (
    MobilityHistory,
    MobilityMeasurements,
    MobilityMethod,
    MobilitySubmission,
    MobilityTestSpec,
)
from app.repositories.mobility import MobilityRepository
from app.rules import mobility
from app.rules import thresholds as t
from app.services.crew_service import CrewService

METHOD = MobilityMethod(
    title="Mobility & Balance Check",
    total_duration_s=120,
    tests=[
        MobilityTestSpec(
            test="balance",
            label="Single-leg balance",
            duration_s=30,
            instructions="Stand on one leg, hands on hips, eyes open. Hold up to 30 seconds.",
            send=["balance_hold_s", "sway_pct_height"],
        ),
        MobilityTestSpec(
            test="sit_to_stand",
            label="5x sit-to-stand",
            duration_s=30,
            instructions="Arms crossed, stand up fully and sit down 5 times as fast as is safe.",
            send=["sit_to_stand_5x_s"],
        ),
        MobilityTestSpec(
            test="squat_rom",
            label="Squat knee bend",
            duration_s=20,
            instructions="Side-on to the camera, do 3 slow bodyweight squats as deep as is comfortable.",
            send=["knee_flexion_deg"],
        ),
    ],
    min_pose_confidence=t.MOBILITY_MIN_CONFIDENCE,
    thresholds={
        "balance_hold_amber_s": t.BALANCE_HOLD_AMBER_S,
        "balance_hold_red_s": t.BALANCE_HOLD_RED_S,
        "sit_to_stand_amber_s": t.SIT_STAND_AMBER_S,
        "sit_to_stand_red_s": t.SIT_STAND_RED_S,
        "knee_flexion_amber_deg": t.KNEE_FLEXION_AMBER_DEG,
        "knee_flexion_red_deg": t.KNEE_FLEXION_RED_DEG,
        "worse_than_first_check_amber": t.MOBILITY_CHANGE_AMBER,
        "worse_than_first_check_red": t.MOBILITY_CHANGE_RED,
    },
    limits=(
        "Measures movement (balance, leg strength, knee range of motion) from body keypoints. "
        "It cannot assess bone health or bone loss, which needs a bone density scan. "
        "Video stays on the device; only these numbers are sent."
    ),
)


class MobilityService:
    def __init__(self, crew: CrewService, repo: MobilityRepository) -> None:
        self._crew = crew
        self._repo = repo

    async def submit(self, astronaut_id: str, day: int, m: MobilityMeasurements) -> MobilitySubmission:
        astro = self._crew.astronaut(astronaut_id)
        reliable = m.pose_confidence >= t.MOBILITY_MIN_CONFIDENCE
        check = await self._repo.add(astro.id, day, m, reliable)
        result = mobility.assess(await self._repo.checks(astro.id))
        message = (
            "Check saved."
            if reliable
            else "Pose tracking was not clear enough to use this check. Retake it in good light, full body in view."
        )
        return MobilitySubmission(check=check, counted=reliable, result=result, message=message)

    async def history(self, astronaut_id: str) -> MobilityHistory:
        astro = self._crew.astronaut(astronaut_id)
        checks = await self._repo.checks(astro.id)
        return MobilityHistory(astronaut_id=astro.id, checks=checks, latest=mobility.assess(checks))

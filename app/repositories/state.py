"""Persistence for everything the app writes at runtime (check-ins, assignments, flags, notes, log...).

The scoring engine reads an in-memory `MissionData`; services write through this repository first
(so a failed write never leaves memory ahead of the database) and `load` rebuilds memory at startup.
There is deliberately no table for Nova chat: conversations are never stored.
"""

import logging
from typing import Any

from app.db.base import Database, DatabaseError, Row
from app.domain.questionnaires import seed_assignments
from app.domain.store import MissionData, SafetyFlag
from app.schemas.actions import ActionLogEntry, CrewMessage
from app.schemas.assessment import Resolution
from app.schemas.crewmode import Assignment
from app.schemas.mobility import MobilityCheck, MobilityMeasurements
from app.schemas.nova import SharedNote
from app.schemas.telemetry import CheckIn

log = logging.getLogger(__name__)

MISSION = "mission"
CHECKINS = "checkins"
ASSIGNMENTS = "assignments"
SAMPLES = "samples"  # only runtime-added samples (questionnaire scores); generated data is deterministic
SAFETY_FLAGS = "safety_flags"
SHARED_NOTES = "shared_notes"
ACTION_LOG = "action_log"
CREW_MESSAGES = "crew_messages"
RESOLUTIONS = "resolutions"
MOBILITY_CHECKS = "mobility_sessions"


class StateRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    # -- mission ------------------------------------------------------------------
    async def launch_epoch_ms(self) -> int | None:
        rows = await self._db.table(MISSION).select(eq={"id": 1}, limit=1)
        return int(rows[0]["launch_epoch_ms"]) if rows else None

    async def save_launch_epoch_ms(self, value: int) -> None:
        await self._db.table(MISSION).upsert([{"id": 1, "launch_epoch_ms": value}], "id")

    # -- writes (each returns after the database accepted the row) -----------------------
    async def save_check_in(self, c: CheckIn) -> None:
        await self._db.table(CHECKINS).upsert(
            [
                {
                    "id": c.id,
                    "crew_id": c.crew_id,
                    "day": c.day,
                    "at": c.at,
                    "mood": c.mood,
                    "sleep_quality": c.sleep_quality,
                    "energy": c.energy,
                    "symptoms": list(c.symptoms),
                    "note": c.note,
                }
            ],
            "crew_id,day",
        )

    async def save_assignment(self, a: Assignment) -> None:
        await self._db.table(ASSIGNMENTS).upsert(
            [
                {
                    "id": a.id,
                    "crew_id": a.crew_id,
                    "questionnaire_id": a.questionnaire_id,
                    "assigned_by": a.assigned_by,
                    "note": a.note,
                    "assigned_at": a.assigned_at,
                    "due_day": a.due_day,
                    "status": a.status,
                    "answers": a.answers,
                    "current_index": a.current_index,
                    "completed_at": a.completed_at,
                    "score": a.score,
                }
            ],
            "id",
        )

    async def save_sample(self, crew_id: str, metric: str, t: float, v: float) -> None:
        await self._db.table(SAMPLES).insert({"crew_id": crew_id, "metric": metric, "t": t, "v": v})

    async def save_safety_flag(self, f: SafetyFlag) -> None:
        # Category and signal only. No text column exists, by design.
        await self._db.table(SAFETY_FLAGS).insert(
            {"id": f.id, "crew_id": f.crew_id, "at": f.at, "category": f.category, "signal": f.signal}
        )

    async def save_note(self, n: SharedNote) -> None:
        await self._db.table(SHARED_NOTES).insert({"id": n.id, "crew_id": n.crew_id, "at": n.at, "text": n.text})

    async def save_log(self, e: ActionLogEntry) -> None:
        await self._db.table(ACTION_LOG).insert(
            {
                "id": e.id,
                "insight_id": e.insight_id,
                "crew_id": e.crew_id,
                "at": e.at,
                "by": e.by,
                "kind": e.kind,
                "label": e.label,
                "detail": e.detail,
            }
        )

    async def save_message(self, m: CrewMessage) -> None:
        await self._db.table(CREW_MESSAGES).insert(
            {
                "id": m.id,
                "crew_id": m.crew_id,
                "from": m.from_,
                "text": m.text,
                "sent_at": m.sent_at,
                "deliver_at": m.deliver_at,
                "insight_id": m.insight_id,
            }
        )

    async def save_resolution(self, insight_id: str, r: Resolution) -> None:
        await self._db.table(RESOLUTIONS).upsert(
            [{"insight_id": insight_id, "at": r.at, "by": r.by, "note": r.note, "severity": r.severity}], "insight_id"
        )

    async def save_mobility_check(self, c: MobilityCheck) -> None:
        m = c.measurements
        await self._db.table(MOBILITY_CHECKS).insert(
            {
                "id": c.id,
                "crew_id": c.crew_id,
                "day": c.day,
                "at": c.at,
                "balance_hold_s": m.balance_hold_s,
                "sway_pct_height": m.sway_pct_height,
                "sit_to_stand_s": m.sit_to_stand_s,
                "knee_flexion_deg": m.knee_flexion_deg,
                "pose_confidence": m.pose_confidence,
                "reliable": c.reliable,
            }
        )

    async def delete_resolution(self, insight_id: str) -> None:
        await self._db.table(RESOLUTIONS).delete({"insight_id": insight_id})

    # -- startup ----------------------------------------------------------------------------
    async def load_into(self, data: MissionData) -> None:
        """Rebuild memory from the database. A database failure leaves the simulated defaults in place."""
        try:
            await self._load(data)
        except DatabaseError as exc:
            log.error("Could not load saved state (%s); starting from the simulated defaults", exc)

    async def _load(self, data: MissionData) -> None:
        db = self._db
        for r in await db.table(CHECKINS).select(order="at"):
            data.add_check_in(
                CheckIn(
                    id=r["id"],
                    crew_id=r["crew_id"],
                    day=r["day"],
                    at=r["at"],
                    mood=r["mood"],
                    sleep_quality=r["sleep_quality"],
                    energy=r["energy"],
                    symptoms=r["symptoms"] or [],
                    note=r.get("note"),
                )
            )
        saved = await db.table(ASSIGNMENTS).select()
        if saved:
            for r in saved:
                data.upsert_assignment(_assignment(r))
        else:
            for a in seed_assignments():
                await self.save_assignment(a)
        for r in await db.table(SAMPLES).select(order="t"):
            data.add_sample(r["crew_id"], r["metric"], r["t"], r["v"])
        for r in await db.table(SAFETY_FLAGS).select(order="at"):
            data.add_safety_flag(SafetyFlag(r["id"], r["crew_id"], r["at"], r["category"], r["signal"]))
        for r in await db.table(SHARED_NOTES).select(order="at"):
            data.add_shared_note(SharedNote(id=r["id"], crew_id=r["crew_id"], at=r["at"], text=r["text"]))
        for r in await db.table(ACTION_LOG).select(order="at"):
            data.add_log(
                ActionLogEntry(
                    id=r["id"],
                    insight_id=r["insight_id"],
                    crew_id=r["crew_id"],
                    at=r["at"],
                    by=r["by"],
                    kind=r["kind"],
                    label=r["label"],
                    detail=r.get("detail"),
                )
            )
        for r in await db.table(CREW_MESSAGES).select(order="sent_at"):
            data.add_message(
                CrewMessage(
                    id=r["id"],
                    crew_id=r["crew_id"],
                    **{"from": r["from"]},
                    text=r["text"],
                    sent_at=r["sent_at"],
                    deliver_at=r["deliver_at"],
                    insight_id=r.get("insight_id"),
                )
            )
        for r in await db.table(MOBILITY_CHECKS).select(order="at"):
            data.add_mobility_check(
                MobilityCheck(
                    id=r["id"],
                    crew_id=r["crew_id"],
                    day=r["day"],
                    at=r["at"],
                    measurements=MobilityMeasurements(
                        balance_hold_s=r["balance_hold_s"],
                        sway_pct_height=r["sway_pct_height"],
                        sit_to_stand_s=r["sit_to_stand_s"],
                        knee_flexion_deg=r["knee_flexion_deg"],
                        pose_confidence=r["pose_confidence"],
                    ),
                    reliable=r["reliable"],
                )
            )
        for r in await db.table(RESOLUTIONS).select():
            data.resolve(r["insight_id"], Resolution(at=r["at"], by=r["by"], note=r["note"], severity=r["severity"]))


def _assignment(r: Row) -> Assignment:
    d: dict[str, Any] = {
        "id": r["id"],
        "crewId": r["crew_id"],
        "questionnaireId": r["questionnaire_id"],
        "assignedBy": r["assigned_by"],
        "note": r.get("note"),
        "assignedAt": r["assigned_at"],
        "dueDay": r["due_day"],
        "status": r["status"],
        "answers": r.get("answers") or {},
        "currentIndex": r["current_index"],
        "completedAt": r.get("completed_at"),
        "score": r.get("score"),
    }
    return Assignment.model_validate(d)

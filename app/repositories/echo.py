"""Persistence for ECHO: chat sessions, their messages and the loneliness assessments."""

import uuid
from datetime import UTC, datetime

from app.db.base import Database
from app.domain.store import MissionData
from app.schemas.echo import ChatRole, EchoMessage, EchoSession, LonelinessAssessment

SESSIONS = "echo_sessions"
MESSAGES = "echo_messages"
ASSESSMENTS = "echo_assessments"


def _now() -> str:
    return datetime.now(UTC).isoformat()


class EchoRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    # -- sessions ----------------------------------------------------------------------------
    async def create_session(self, crew_id: str, day: int) -> EchoSession:
        row = await self._db.table(SESSIONS).insert(
            {
                "id": str(uuid.uuid4()),
                "crew_id": crew_id,
                "mission_day": day,
                "status": "active",
                "created_at": _now(),
                "completed_at": None,
            }
        )
        return EchoSession.model_validate(row)

    async def get_session(self, session_id: str) -> EchoSession | None:
        rows = await self._db.table(SESSIONS).select(eq={"id": session_id}, limit=1)
        return EchoSession.model_validate(rows[0]) if rows else None

    async def complete_session(self, session_id: str) -> None:
        await self._db.table(SESSIONS).update({"id": session_id}, {"status": "completed", "completed_at": _now()})

    # -- messages ----------------------------------------------------------------------------
    async def add_message(self, session_id: str, role: ChatRole, content: str) -> EchoMessage:
        row = await self._db.table(MESSAGES).insert(
            {"id": str(uuid.uuid4()), "session_id": session_id, "role": role, "content": content, "created_at": _now()}
        )
        return EchoMessage.model_validate(row)

    async def messages(self, session_id: str) -> list[EchoMessage]:
        rows = await self._db.table(MESSAGES).select(eq={"session_id": session_id}, order="created_at")
        return [EchoMessage.model_validate(r) for r in rows]

    # -- assessments -------------------------------------------------------------------------
    async def add_assessment(self, assessment: LonelinessAssessment) -> None:
        await self._db.table(ASSESSMENTS).insert(assessment.model_dump(mode="json"))

    async def assessment_for_session(self, session_id: str) -> LonelinessAssessment | None:
        rows = await self._db.table(ASSESSMENTS).select(eq={"session_id": session_id}, limit=1)
        return LonelinessAssessment.model_validate(rows[0]) if rows else None

    async def load_into(self, data: MissionData) -> None:
        """Rebuild the in-memory assessments (what the Isolation hazard reads) from the database."""
        for r in await self._db.table(ASSESSMENTS).select(order="at"):
            data.add_echo_assessment(LonelinessAssessment.model_validate(r))

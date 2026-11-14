import uuid
from datetime import UTC, datetime

from app.db.base import Database
from app.models.isolation import (
    ChatMessage,
    ChatRole,
    ChatSession,
    LonelinessAssessment,
    SessionStatus,
)

SESSIONS = "isolation_chat_sessions"
MESSAGES = "isolation_chat_messages"
ASSESSMENTS = "loneliness_assessments"


def _now() -> str:
    return datetime.now(UTC).isoformat()


class IsolationRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    # -- sessions ----------------------------------------------------------------
    async def create_session(self, astronaut_id: str, day: int) -> ChatSession:
        row = await self._db.table(SESSIONS).insert(
            {
                "id": str(uuid.uuid4()),
                "astronaut_id": astronaut_id,
                "mission_day": day,
                "status": SessionStatus.ACTIVE.value,
                "created_at": _now(),
                "completed_at": None,
            }
        )
        return ChatSession.model_validate(row)

    async def get_session(self, session_id: str) -> ChatSession | None:
        rows = await self._db.table(SESSIONS).select(eq={"id": session_id}, limit=1)
        return ChatSession.model_validate(rows[0]) if rows else None

    async def complete_session(self, session_id: str) -> None:
        await self._db.table(SESSIONS).update(
            {"id": session_id}, {"status": SessionStatus.COMPLETED.value, "completed_at": _now()}
        )

    # -- messages ----------------------------------------------------------------
    async def add_message(self, session_id: str, role: ChatRole, content: str) -> ChatMessage:
        row = await self._db.table(MESSAGES).insert(
            {
                "id": str(uuid.uuid4()),
                "session_id": session_id,
                "role": role.value,
                "content": content,
                "created_at": _now(),
            }
        )
        return ChatMessage.model_validate(row)

    async def messages(self, session_id: str) -> list[ChatMessage]:
        rows = await self._db.table(MESSAGES).select(eq={"session_id": session_id}, order="created_at")
        return [ChatMessage.model_validate(r) for r in rows]

    # -- assessments ---------------------------------------------------------------
    async def add_assessment(self, assessment: LonelinessAssessment) -> None:
        await self._db.table(ASSESSMENTS).insert(assessment.model_dump(mode="json"))

    async def assessment_for_session(self, session_id: str) -> LonelinessAssessment | None:
        rows = await self._db.table(ASSESSMENTS).select(eq={"session_id": session_id}, limit=1)
        return LonelinessAssessment.model_validate(rows[0]) if rows else None

    async def assessments(self, astronaut_id: str | None = None) -> list[LonelinessAssessment]:
        """Oldest first; every astronaut when `astronaut_id` is None."""
        eq = {"astronaut_id": astronaut_id} if astronaut_id else None
        rows = await self._db.table(ASSESSMENTS).select(eq=eq, order="created_at")
        return [LonelinessAssessment.model_validate(r) for r in rows]

"""ECHO check-ins: a chat session with the companion, then a loneliness score.

Flow: `start` opens a session, `send` exchanges messages (3 to 10 astronaut replies), `complete` has the
rater score the transcript (idempotent). The score lands in the Isolation hazard and, when it is elevated,
becomes a finding for Mission Control. See `app.domain.loneliness` for the scoring rules.
"""

import asyncio
import uuid
from datetime import UTC, datetime

from app.core.errors import (
    CompanionUnavailableError,
    NotEnoughTurnsError,
    SessionClosedError,
    SessionNotFoundError,
    SessionTurnLimitError,
    UnknownAstronautError,
)
from app.domain import loneliness
from app.domain.mission_plan import hour_to_day
from app.domain.store import MissionData
from app.repositories.echo import EchoRepository
from app.schemas.crew import Astronaut
from app.schemas.echo import (
    EchoHistory,
    EchoHistoryItem,
    EchoMessage,
    EchoMethod,
    EchoSession,
    EchoSessionDetail,
    EchoTurnResponse,
    LonelinessAssessment,
    StartEchoResponse,
)
from app.services.clock import MissionClock
from app.services.echo_companion import EchoCompanion, opening_message

METHOD = EchoMethod(
    instrument="Three-Item Loneliness Scale, rated from a conversational AI check-in",
    source="Hughes, Waite, Hawkley & Cacioppo (2004), Research on Aging 26(6)",
    items=list(loneliness.ITEMS),
    item_scale={"1": "Hardly ever", "2": "Some of the time", "3": "Often"},
    score_range=[loneliness.SCORE_MIN, loneliness.SCORE_MAX],
    min_turns=loneliness.MIN_TURNS,
    max_turns=loneliness.MAX_TURNS,
    min_confidence=loneliness.MIN_CONFIDENCE,
    bands={
        "nominal": f"{loneliness.SCORE_MIN}-{loneliness.WATCH_MIN - 1}",
        "watch": f"{loneliness.WATCH_MIN} and above",
        "alert": f"{loneliness.ALERT_MIN} and above for {loneliness.ALERT_DAYS} consecutive days, or a safety "
        "concern (our rule, illustrative)",
        "unreliable": f"confidence below {loneliness.MIN_CONFIDENCE}: stored, capped at watch, not used by the hazard",
    },
)


class EchoService:
    def __init__(
        self, data: MissionData, clock: MissionClock, repo: EchoRepository, companion: EchoCompanion | None
    ) -> None:
        self._data = data
        self._clock = clock
        self._repo = repo
        self._companion = companion

    @property
    def enabled(self) -> bool:
        return self._companion is not None

    def _require_companion(self) -> EchoCompanion:
        if self._companion is None:
            raise CompanionUnavailableError("GEMINI_API_KEY is not configured")
        return self._companion

    def _astronaut(self, crew_id: str) -> Astronaut:
        astro = self._data.astronaut(crew_id)
        if astro is None:
            raise UnknownAstronautError(crew_id)
        return astro

    async def _session(
        self, crew_id: str, session_id: str, *, with_messages: bool
    ) -> tuple[EchoSession, list[EchoMessage]]:
        """Load the session (and its transcript) in parallel; 404 if it isn't this astronaut's."""
        astro = self._astronaut(crew_id)
        try:
            uuid.UUID(session_id)
        except ValueError:
            raise SessionNotFoundError(session_id) from None
        if with_messages:
            session, messages = await asyncio.gather(
                self._repo.get_session(session_id), self._repo.messages(session_id)
            )
        else:
            session, messages = await self._repo.get_session(session_id), []
        if session is None or session.crew_id != astro.id:
            raise SessionNotFoundError(session_id)
        return session, messages

    # -- chat ------------------------------------------------------------------------------------
    async def start(self, crew_id: str) -> StartEchoResponse:
        astro = self._astronaut(crew_id)
        self._require_companion()
        day = hour_to_day(self._clock.now_hour())
        session = await self._repo.create_session(astro.id, day)
        opener = await self._repo.add_message(session.id, "assistant", opening_message(astro, day))
        return StartEchoResponse(
            session=session, messages=[opener], min_turns=loneliness.MIN_TURNS, max_turns=loneliness.MAX_TURNS
        )

    async def send(self, crew_id: str, session_id: str, content: str) -> EchoTurnResponse:
        companion = self._require_companion()
        session, transcript = await self._session(crew_id, session_id, with_messages=True)
        if session.status != "active":
            raise SessionClosedError
        turns = _astronaut_turns(transcript)
        if turns >= loneliness.MAX_TURNS:
            raise SessionTurnLimitError(loneliness.MAX_TURNS)

        # Ask ECHO first and save both messages only if it answered, so a failed call leaves no orphaned
        # message behind and the client can simply resend.
        said = EchoMessage(
            id="pending", session_id=session.id, role="astronaut", content=content.strip(), created_at=datetime.now(UTC)
        )
        turns += 1
        text = await companion.reply(
            self._astronaut(crew_id), session.mission_day, [*transcript, said], loneliness.MAX_TURNS - turns
        )
        await self._repo.add_message(session.id, "astronaut", said.content)
        reply = await self._repo.add_message(session.id, "assistant", text)
        return EchoTurnResponse(
            session_id=session.id,
            reply=reply,
            astronaut_turns=turns,
            can_complete=turns >= loneliness.MIN_TURNS,
            must_complete=turns >= loneliness.MAX_TURNS,
        )

    async def complete(self, crew_id: str, session_id: str) -> LonelinessAssessment:
        companion = self._require_companion()
        session, _ = await self._session(crew_id, session_id, with_messages=False)
        existing = await self._repo.assessment_for_session(session.id)
        if existing is not None:
            return existing  # idempotent: completing twice returns the same score
        transcript = await self._repo.messages(session.id)
        turns = _astronaut_turns(transcript)
        if turns < loneliness.MIN_TURNS:
            raise NotEnoughTurnsError(turns, loneliness.MIN_TURNS)

        astro = self._astronaut(crew_id)
        rating = await companion.rate(astro, session.mission_day, transcript)
        assessment = loneliness.score_rating(
            rating,
            loneliness.day_scores(self._data.echo_assessments(astro.id)),
            session_id=session.id,
            crew_id=astro.id,
            day=session.mission_day,
            at=self._clock.now_hour(),
            model=companion.model,
        )
        await self._repo.add_assessment(assessment)
        await self._repo.complete_session(session.id)
        self._data.add_echo_assessment(assessment)
        return assessment

    async def detail(self, crew_id: str, session_id: str) -> EchoSessionDetail:
        session, messages = await self._session(crew_id, session_id, with_messages=True)
        return EchoSessionDetail(
            session=session, messages=messages, assessment=await self._repo.assessment_for_session(session.id)
        )

    def history(self, crew_id: str) -> EchoHistory:
        astro = self._astronaut(crew_id)
        return EchoHistory(
            crew_id=astro.id,
            items=[
                EchoHistoryItem(
                    day=a.mission_day,
                    score=a.score,
                    status=a.status,
                    confidence=a.confidence,
                    reliable=a.reliable,
                    session_id=a.session_id,
                )
                for a in self._data.echo_assessments(astro.id)
            ],
        )


def _astronaut_turns(transcript: list[EchoMessage]) -> int:
    return sum(1 for m in transcript if m.role == "astronaut")

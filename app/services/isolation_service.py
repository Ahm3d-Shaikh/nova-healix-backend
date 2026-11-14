"""AI isolation check-ins: chat sessions with the companion, then a loneliness score and alert.

Scoring algorithm (deterministic once the rater has answered):
  1. The rater returns Three-Item Loneliness Scale ratings q1-q3 (1-3 each), confidence and a safety flag.
  2. score = q1 + q2 + q3 (3-9).
  3. Level from app.rules.isolation over the astronaut's daily series (prior days + today's score):
     green 3-5, amber >= 6, red >= 7 for 3 consecutive days, or red at once on a safety concern.
  4. confidence < CHECKIN_MIN_CONFIDENCE -> stored as unreliable: it never drives the Isolation card
     and is capped at amber (a safety concern still escalates to red).
"""

import uuid
from datetime import UTC, datetime

from app.core.errors import (
    CompanionUnavailableError,
    NotEnoughTurnsError,
    SessionClosedError,
    SessionNotFoundError,
    SessionTurnLimitError,
)
from app.models.enums import Level
from app.models.isolation import (
    ChatMessage,
    ChatRole,
    ChatSession,
    ChatSessionDetail,
    ChatTurnResponse,
    IsolationHistory,
    IsolationHistoryItem,
    LonelinessAssessment,
    LonelinessRating,
    ScoringMethod,
    SessionStatus,
    StartSessionResponse,
)
from app.repositories.isolation import IsolationRepository
from app.rules import isolation as rule
from app.rules import thresholds as t
from app.services.companion import Companion, opening_message
from app.services.crew_service import CrewService

METHOD = ScoringMethod(
    instrument="Three-Item Loneliness Scale, rated from a conversational AI check-in",
    source="Hughes, Waite, Hawkley & Cacioppo (2004), Research on Aging 26(6)",
    items=list(rule.ITEMS),
    item_scale={1: "Hardly ever", 2: "Some of the time", 3: "Often"},
    score_range=(t.LONELINESS_MIN, t.LONELINESS_MAX),
    min_turns=t.CHECKIN_MIN_TURNS,
    max_turns=t.CHECKIN_MAX_TURNS,
    min_confidence=t.CHECKIN_MIN_CONFIDENCE,
    bands={
        "green": f"{t.LONELINESS_MIN}-{t.LONELINESS_AMBER_MIN - 1}",
        "amber": f">= {t.LONELINESS_AMBER_MIN}",
        "red": f">= {t.LONELINESS_RED_MIN} for {t.LONELINESS_RED_DAYS} consecutive days, or a safety concern "
        "(our rule, illustrative)",
        "unreliable": f"confidence < {t.CHECKIN_MIN_CONFIDENCE}: stored, capped at amber, not used on the card",
    },
)


class IsolationService:
    def __init__(self, crew: CrewService, repo: IsolationRepository, companion: Companion | None) -> None:
        self._crew = crew
        self._repo = repo
        self._companion = companion

    def _require_companion(self) -> Companion:
        if self._companion is None:
            raise CompanionUnavailableError("GEMINI_API_KEY is not configured")
        return self._companion

    async def _session(self, astronaut_id: str, session_id: str) -> ChatSession:
        astro = self._crew.astronaut(astronaut_id)
        try:
            uuid.UUID(session_id)
        except ValueError:
            raise SessionNotFoundError(session_id) from None
        session = await self._repo.get_session(session_id)
        if session is None or session.astronaut_id != astro.id:
            raise SessionNotFoundError(session_id)
        return session

    # -- chat -------------------------------------------------------------------------
    async def start(self, astronaut_id: str, day: int) -> StartSessionResponse:
        astro = self._crew.astronaut(astronaut_id)
        self._require_companion()
        session = await self._repo.create_session(astro.id, day)
        opener = await self._repo.add_message(session.id, ChatRole.ASSISTANT, opening_message(astro, day))
        return StartSessionResponse(
            session=session, messages=[opener], min_turns=t.CHECKIN_MIN_TURNS, max_turns=t.CHECKIN_MAX_TURNS
        )

    async def send(self, astronaut_id: str, session_id: str, content: str) -> ChatTurnResponse:
        companion = self._require_companion()
        session = await self._session(astronaut_id, session_id)
        if session.status != SessionStatus.ACTIVE:
            raise SessionClosedError
        transcript = await self._repo.messages(session.id)
        turns = _astronaut_turns(transcript)
        if turns >= t.CHECKIN_MAX_TURNS:
            raise SessionTurnLimitError(t.CHECKIN_MAX_TURNS)

        said = await self._repo.add_message(session.id, ChatRole.ASTRONAUT, content.strip())
        turns += 1
        astro = self._crew.astronaut(session.astronaut_id)
        text = await companion.reply(astro, session.mission_day, [*transcript, said], t.CHECKIN_MAX_TURNS - turns)
        reply = await self._repo.add_message(session.id, ChatRole.ASSISTANT, text)
        return ChatTurnResponse(
            session_id=session.id,
            reply=reply,
            astronaut_turns=turns,
            can_complete=turns >= t.CHECKIN_MIN_TURNS,
            must_complete=turns >= t.CHECKIN_MAX_TURNS,
        )

    async def complete(self, astronaut_id: str, session_id: str) -> LonelinessAssessment:
        companion = self._require_companion()
        session = await self._session(astronaut_id, session_id)
        existing = await self._repo.assessment_for_session(session.id)
        if existing is not None:
            return existing  # idempotent: completing twice returns the same score
        transcript = await self._repo.messages(session.id)
        turns = _astronaut_turns(transcript)
        if turns < t.CHECKIN_MIN_TURNS:
            raise NotEnoughTurnsError(turns, t.CHECKIN_MIN_TURNS)

        astro = self._crew.astronaut(session.astronaut_id)
        rating = await companion.rate(astro, session.mission_day, transcript)
        prior = await self._crew.loneliness_series(astro.id, session.mission_day - 1)
        assessment = score_rating(
            rating,
            prior,
            session_id=session.id,
            astronaut_id=astro.id,
            day=session.mission_day,
            model=companion.model,
        )
        await self._repo.add_assessment(assessment)
        await self._repo.complete_session(session.id)
        return assessment

    async def detail(self, astronaut_id: str, session_id: str) -> ChatSessionDetail:
        session = await self._session(astronaut_id, session_id)
        return ChatSessionDetail(
            session=session,
            messages=await self._repo.messages(session.id),
            assessment=await self._repo.assessment_for_session(session.id),
        )

    async def history(self, astronaut_id: str) -> IsolationHistory:
        astro = self._crew.astronaut(astronaut_id)
        items = [
            IsolationHistoryItem(
                day=r.day, source="simulated", score=r.loneliness_q1 + r.loneliness_q2 + r.loneliness_q3
            )
            for r in self._crew.records(astro.id)
        ]
        items += [
            IsolationHistoryItem(
                day=a.mission_day,
                source="ai_checkin",
                score=a.score,
                level=a.level,
                confidence=a.confidence,
                reliable=a.reliable,
                session_id=a.session_id,
            )
            for a in await self._repo.assessments(astro.id)
        ]
        return IsolationHistory(astronaut_id=astro.id, items=items)


def score_rating(
    rating: LonelinessRating,
    prior_totals: list[int],
    *,
    session_id: str,
    astronaut_id: str,
    day: int,
    model: str,
) -> LonelinessAssessment:
    """Turn a rater response into a stored assessment (pure function; see module docstring)."""
    q1, q2, q3 = rating.lack_companionship.rating, rating.left_out.rating, rating.isolated.rating
    score = q1 + q2 + q3
    confidence = min(1.0, max(0.0, rating.confidence))
    reliable = confidence >= t.CHECKIN_MIN_CONFIDENCE
    series = [*prior_totals, score]
    alert = rule.assess(series, safety_concern=rating.safety_concern)
    if not reliable and alert.level == Level.RED and not rating.safety_concern:
        alert = alert.model_copy(update={"level": Level.AMBER})
    if not reliable:
        alert = alert.model_copy(
            update={
                "what": f"{alert.what} Low-confidence rating ({confidence:.0%}).",
                "action": f"{alert.action} Repeat the check-in with more detail to confirm.",
            }
        )
    return LonelinessAssessment(
        id=str(uuid.uuid4()),
        session_id=session_id,
        astronaut_id=astronaut_id,
        mission_day=day,
        q1=q1,
        q2=q2,
        q3=q3,
        score=score,
        confidence=round(confidence, 3),
        reliable=reliable,
        safety_concern=rating.safety_concern,
        level=alert.level,
        consecutive_days_at_or_above_7=rule.high_streak(series),
        rationale=rating.rationale,
        evidence=[rating.lack_companionship.evidence, rating.left_out.evidence, rating.isolated.evidence],
        alert=alert,
        model=model,
        created_at=datetime.now(UTC),
    )


def _astronaut_turns(transcript: list[ChatMessage]) -> int:
    return sum(1 for m in transcript if m.role == ChatRole.ASTRONAUT)

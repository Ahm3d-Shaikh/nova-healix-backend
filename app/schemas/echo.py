"""ECHO: the scored isolation check-in chat. Unlike Nova it is stored: the transcript and the loneliness score
are kept so Mission Control can follow the trend."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.base import CamelModel
from app.schemas.crew import Status

ChatRole = Literal["assistant", "astronaut"]
SessionStatus = Literal["active", "completed"]


class EchoMessage(CamelModel):
    id: str
    session_id: str
    role: ChatRole
    content: str
    created_at: datetime


class EchoSession(CamelModel):
    id: str
    crew_id: str
    mission_day: int
    status: SessionStatus
    created_at: datetime
    completed_at: datetime | None = None


class EchoMessageIn(CamelModel):
    content: str = Field(min_length=1, max_length=2000, description="What the astronaut says")


class StartEchoResponse(CamelModel):
    session: EchoSession
    messages: list[EchoMessage]
    min_turns: int
    max_turns: int


class EchoTurnResponse(CamelModel):
    session_id: str
    reply: EchoMessage
    astronaut_turns: int
    can_complete: bool  # enough replies to score
    must_complete: bool  # reply limit reached; call /complete


# --- What the rater model returns (structured output; plain models so the JSON schema stays snake_case) ----------
class ItemRating(BaseModel):
    rating: int = Field(ge=1, le=3, description="1 = hardly ever, 2 = some of the time, 3 = often")
    evidence: str = Field(description="Short quote or paraphrase from the astronaut, or 'no evidence'")


class LonelinessRating(BaseModel):
    lack_companionship: ItemRating
    left_out: ItemRating
    isolated: ItemRating
    confidence: float = Field(description="0-1: how well the transcript supports these ratings")
    safety_concern: bool = Field(description="True if the astronaut expressed hopelessness, self-harm or not coping")
    rationale: str = Field(description="One or two sentences explaining the ratings")


# --- Stored / returned assessment ----------------------------------------------------------------------------------
class LonelinessAssessment(CamelModel):
    id: str
    session_id: str
    crew_id: str
    mission_day: int
    at: float  # mission hour scored
    q1: int
    q2: int
    q3: int
    score: int  # 3-9
    confidence: float
    reliable: bool  # confidence high enough to drive the Isolation hazard
    safety_concern: bool
    status: Status
    consecutive_high_days: int  # consecutive days ending today with a score at or above 7
    rationale: str
    evidence: list[str]
    what: str
    why: str
    action: str
    source: str
    model: str
    created_at: datetime


class EchoSessionDetail(CamelModel):
    session: EchoSession
    messages: list[EchoMessage]
    assessment: LonelinessAssessment | None


class EchoMethod(CamelModel):
    instrument: str
    source: str
    items: list[str]
    item_scale: dict[str, str]
    score_range: list[int]
    min_turns: int
    max_turns: int
    min_confidence: float
    bands: dict[str, str]


class EchoHistoryItem(CamelModel):
    day: int
    score: int
    status: Status
    confidence: float
    reliable: bool
    session_id: str


class EchoHistory(CamelModel):
    crew_id: str
    items: list[EchoHistoryItem]

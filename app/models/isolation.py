from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.models.alert import Alert
from app.models.enums import Level


class ChatRole(StrEnum):
    ASSISTANT = "assistant"
    ASTRONAUT = "astronaut"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"


class ChatMessage(BaseModel):
    id: str
    session_id: str
    role: ChatRole
    content: str
    created_at: datetime


class ChatSession(BaseModel):
    id: str
    astronaut_id: str
    mission_day: int
    status: SessionStatus
    created_at: datetime
    completed_at: datetime | None = None


class ChatMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000, description="What the astronaut says")


class StartSessionResponse(BaseModel):
    session: ChatSession
    messages: list[ChatMessage]
    min_turns: int
    max_turns: int


class ChatTurnResponse(BaseModel):
    session_id: str
    reply: ChatMessage
    astronaut_turns: int
    can_complete: bool  # enough replies to score
    must_complete: bool  # reply limit reached; call /complete


# --- What the rater model returns (structured output) -------------------------------
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


# --- Stored / returned assessment ---------------------------------------------------
class LonelinessAssessment(BaseModel):
    id: str
    session_id: str
    astronaut_id: str
    mission_day: int
    q1: int
    q2: int
    q3: int
    score: int
    confidence: float
    reliable: bool  # confidence >= threshold; only reliable scores drive the Isolation card
    safety_concern: bool
    level: Level
    consecutive_days_at_or_above_7: int
    rationale: str
    evidence: list[str]
    alert: Alert
    model: str
    created_at: datetime


class ChatSessionDetail(BaseModel):
    session: ChatSession
    messages: list[ChatMessage]
    assessment: LonelinessAssessment | None


class ScoringMethod(BaseModel):
    instrument: str
    source: str
    items: list[str]
    item_scale: dict[int, str]
    score_range: tuple[int, int]
    min_turns: int
    max_turns: int
    min_confidence: float
    bands: dict[str, str]


class IsolationHistoryItem(BaseModel):
    day: int
    source: str  # "simulated" | "ai_checkin"
    score: int
    level: Level | None = None
    confidence: float | None = None
    reliable: bool | None = None
    session_id: str | None = None


class IsolationHistory(BaseModel):
    astronaut_id: str
    items: list[IsolationHistoryItem]

from typing import Annotated, Literal

from pydantic import Field

from app.schemas.base import CamelModel
from app.schemas.telemetry import CheckInDraft

SafetyCategory = Literal["self-harm", "medical"]
SafetySignal = Literal[
    "wish-to-die",
    "suicidal-thoughts",
    "self-harm-intent",
    "confirmed-when-asked",
    "chest-pain",
    "breathing",
    "stroke-signs",
    "unconscious",
    "vision-loss",
    "severe-headache",
    "seizure",
]
CardStatus = Literal["proposed", "sent", "dismissed"]


class CheckInCard(CamelModel):
    kind: Literal["checkin"] = "checkin"
    draft: CheckInDraft
    status: CardStatus


class ShareCard(CamelModel):
    kind: Literal["share"] = "share"
    text: str
    status: CardStatus


class SafetyCard(CamelModel):
    kind: Literal["safety"] = "safety"
    category: SafetyCategory


class BreathingCard(CamelModel):
    kind: Literal["breathing"] = "breathing"


ChatCard = Annotated[CheckInCard | ShareCard | SafetyCard | BreathingCard, Field(discriminator="kind")]


class CompanionState(CamelModel):
    pending_safety_check: bool = False
    awaiting_check_in: bool = False


class HistoryTurn(CamelModel):
    role: Literal["astronaut", "nova"]
    text: str = Field(max_length=4000)


class CompanionRequest(CamelModel):
    text: str | None = Field(default=None, max_length=2000)
    history: list[HistoryTurn] = Field(default_factory=list, max_length=16)
    state: CompanionState = Field(default_factory=CompanionState)


class NovaReply(CamelModel):
    omit_when_none = frozenset({"card"})

    text: str
    card: ChatCard | None = None


class SafetyInfo(CamelModel):
    category: SafetyCategory
    signal: SafetySignal


class CompanionTurn(CamelModel):
    omit_when_none = frozenset({"safety"})

    replies: list[NovaReply]
    state: CompanionState
    safety: SafetyInfo | None = None


class SharedNote(CamelModel):
    id: str
    crew_id: str
    at: float
    text: str


class SharedNoteBody(CamelModel):
    text: str = Field(min_length=1, max_length=2000)

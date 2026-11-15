from pydantic import Field

from app.schemas.assessment import LogKind, Severity
from app.schemas.base import CamelModel


class ActionLogEntry(CamelModel):
    omit_when_none = frozenset({"detail"})

    id: str
    insight_id: str
    crew_id: str | None
    at: float
    by: str
    kind: LogKind
    label: str
    detail: str | None = None


class RecordActionBody(CamelModel):
    omit_when_none = frozenset({"detail"})

    insight_id: str = Field(min_length=1)
    crew_id: str | None = None
    kind: LogKind
    label: str = Field(min_length=1, max_length=300)
    detail: str | None = Field(default=None, max_length=2000)


class CrewMessage(CamelModel):
    omit_when_none = frozenset({"insight_id"})

    id: str
    crew_id: str
    from_: str = Field(alias="from")
    text: str
    sent_at: float
    deliver_at: float
    insight_id: str | None = None


class SendMessageBody(CamelModel):
    text: str = Field(min_length=1, max_length=2000)
    insight_id: str | None = None


class ResolveBody(CamelModel):
    crew_id: str | None = None
    note: str = Field(min_length=1, max_length=1000)
    severity: Severity


class ReopenBody(CamelModel):
    crew_id: str | None = None

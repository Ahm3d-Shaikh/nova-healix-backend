"""Mission Control actions: action log, crew messages (with signal delay), resolve and reopen findings."""

import uuid

from app.core.errors import DomainError, UnknownAstronautError
from app.domain.format import format_delay
from app.domain.link import link_state_at
from app.domain.store import MissionData
from app.repositories.state import StateRepository
from app.schemas.actions import ActionLogEntry, CrewMessage, RecordActionBody
from app.schemas.assessment import Resolution, Severity
from app.schemas.crew import Astronaut
from app.services.clock import MissionClock, Trajectory


class ActionsService:
    def __init__(
        self, data: MissionData, clock: MissionClock, trajectory: Trajectory, repo: StateRepository, surgeon: str
    ) -> None:
        self._data = data
        self._clock = clock
        self._trajectory = trajectory
        self._repo = repo
        self._surgeon = surgeon

    @staticmethod
    def _id(prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex[:10]}"

    def _astronaut(self, crew_id: str) -> Astronaut:
        astro = self._data.astronaut(crew_id)
        if astro is None:
            raise UnknownAstronautError(crew_id)
        return astro

    def _check_crew(self, crew_id: str | None) -> None:
        """A finding may concern the whole crew (None); otherwise the astronaut must exist."""
        if crew_id is not None:
            self._astronaut(crew_id)

    async def _log(self, **kw: object) -> ActionLogEntry:
        entry = ActionLogEntry(id=self._id("log"), at=self._clock.now_hour(), by=self._surgeon, **kw)
        await self._repo.save_log(entry)
        self._data.add_log(entry)
        return entry

    def log(self) -> list[ActionLogEntry]:
        return list(self._data.action_log())

    async def record(self, body: RecordActionBody) -> ActionLogEntry:
        if body.kind in ("resolve", "reopen"):
            raise DomainError(f"'{body.kind}' has its own endpoint")
        self._check_crew(body.crew_id)
        return await self._log(
            insight_id=body.insight_id, crew_id=body.crew_id, kind=body.kind, label=body.label, detail=body.detail
        )

    def messages(self, crew_id: str) -> list[CrewMessage]:
        self._astronaut(crew_id)
        return list(self._data.crew_messages(crew_id))

    async def send_message(self, crew_id: str, text: str, insight_id: str | None) -> CrewMessage:
        astro = self._astronaut(crew_id)
        sent = self._clock.now_hour()
        delay_seconds = link_state_at(self._trajectory.au, sent, False).delay_seconds
        msg = CrewMessage(
            id=self._id("msg"),
            crew_id=crew_id,
            **{"from": self._surgeon},
            text=text,
            sent_at=sent,
            deliver_at=sent + delay_seconds / 3600,
            insight_id=insight_id,
        )
        await self._repo.save_message(msg)
        self._data.add_message(msg)
        if insight_id:
            await self._log(
                insight_id=insight_id,
                crew_id=crew_id,
                kind="message",
                label=f"Messaged {astro.name}",
                detail=f"“{text}” · arrives {format_delay(delay_seconds)} later",
            )
        return msg

    async def resolve(self, insight_id: str, crew_id: str | None, note: str, severity: Severity) -> Resolution:
        self._check_crew(crew_id)
        r = Resolution(at=self._clock.now_hour(), by=self._surgeon, note=note, severity=severity)
        await self._repo.save_resolution(insight_id, r)
        self._data.resolve(insight_id, r)
        await self._log(insight_id=insight_id, crew_id=crew_id, kind="resolve", label="Resolved", detail=note)
        return r

    async def reopen(self, insight_id: str, crew_id: str | None) -> None:
        self._check_crew(crew_id)
        await self._repo.delete_resolution(insight_id)
        self._data.reopen(insight_id)
        await self._log(insight_id=insight_id, crew_id=crew_id, kind="reopen", label="Reopened", detail=None)

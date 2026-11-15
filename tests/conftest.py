"""Fixtures for both APIs in the one service.

* v2 (Nova Healix): `container`, `hour`, `replier`.
* RIDGE (ECHO chat, dashboard, distance): `offline_container` (the RIDGE container), `companion` (scripted ECHO).
* `api` is the one combined app (both containers on one in-memory database).
"""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from app.container import build_container
from app.core.config import Settings
from app.db.memory import InMemoryDatabase
from app.main import create_app
from app.models.crew import Astronaut
from app.models.isolation import ChatMessage, ItemRating, LonelinessRating
from app.models.settings import MissionSettings
from app.ridge_container import build_ridge_container
from app.services.donki_client import DonkiClient
from app.services.horizons_client import HorizonsClient

# Mission day 142, 14:00 UTC: the moment the frontend's calibration output was recorded.
NOW_MS = datetime(2026, 11, 14, 14, 0, tzinfo=UTC).timestamp() * 1000


def make_client(handler) -> DonkiClient:
    return DonkiClient(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)), "https://donki.test", "KEY", backoff=0
    )


def make_horizons(handler) -> HorizonsClient:
    return HorizonsClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)), "https://horizons.test")


def failing(request: httpx.Request) -> httpx.Response:
    return httpx.Response(500)


def rating(q1: int = 1, q2: int = 1, q3: int = 1, confidence: float = 0.9, safety: bool = False) -> LonelinessRating:
    return LonelinessRating(
        lack_companionship=ItemRating(rating=q1, evidence="e1"),
        left_out=ItemRating(rating=q2, evidence="e2"),
        isolated=ItemRating(rating=q3, evidence="e3"),
        confidence=confidence,
        safety_concern=safety,
        rationale="test",
    )


class FakeCompanion:
    """Scripted stand-in for Gemini (ECHO): echoes replies and returns a preset rating."""

    model = "fake-model"

    def __init__(self) -> None:
        self.next_rating = rating()
        self.reply_calls: list[tuple[int, int]] = []  # (transcript length, replies left)
        self.fail_next: Exception | None = None  # raise this from the next reply()

    async def reply(self, astronaut: Astronaut, day: int, transcript: Sequence[ChatMessage], replies_left: int) -> str:
        self.reply_calls.append((len(transcript), replies_left))
        if self.fail_next is not None:
            exc, self.fail_next = self.fail_next, None
            raise exc
        return f"ECHO heard: {transcript[-1].content}"

    async def rate(self, astronaut: Astronaut, day: int, transcript: Sequence[ChatMessage]) -> LonelinessRating:
        return self.next_rating


class FakeReplier:
    """Scripted stand-in for Gemini (Nova's open-ended replies)."""

    mode = "gemini"

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail = False

    async def reply(self, name, history, text):
        from app.core.errors import CompanionUnavailableError

        if self.fail:
            raise CompanionUnavailableError("rate limit reached, retry shortly")
        self.calls.append(text)
        return f"GEMINI heard {len(history)} turns"


@pytest.fixture
def settings() -> Settings:
    return Settings(supabase_url="", supabase_service_role_key="", gemini_api_key="", launch_epoch_ms=None)


@pytest.fixture
def db() -> InMemoryDatabase:
    return InMemoryDatabase()


@pytest.fixture
def companion() -> FakeCompanion:
    return FakeCompanion()


@pytest.fixture
def replier() -> FakeReplier:
    return FakeReplier()


@pytest.fixture
def container(settings, db):
    """The v2 (Nova Healix) container."""
    return asyncio.run(build_container(settings, db, now_ms=NOW_MS))


@pytest.fixture
def offline_container(settings, db, companion):
    """The RIDGE container: NASA calls always fail -> serves the bundled snapshots."""
    return asyncio.run(build_ridge_container(settings, make_client(failing), make_horizons(failing), db, companion))


@pytest.fixture
def api(settings, container, offline_container):
    with TestClient(create_app(settings, container, offline_container)) as client:
        yield client


@pytest.fixture
def hour(container) -> float:
    return container.clock.now_hour()


def combined_app(settings: Settings, ridge, db: InMemoryDatabase | None = None):
    """The one app from a RIDGE container; the v2 container is built on the same (or a fresh) database."""
    v2 = asyncio.run(build_container(settings, db or InMemoryDatabase(), now_ms=NOW_MS))
    return create_app(settings, v2, ridge)


def set_settings(api: TestClient, mission: str = "mars", deep_space_mode: bool = False, current_day: int = 5) -> None:
    """Change the saved RIDGE mission settings (there is no public settings endpoint)."""
    service = api.app.state.ridge.mission_settings
    asyncio.run(
        service.update(MissionSettings(mission=mission, deep_space_mode=deep_space_mode, current_day=current_day))
    )

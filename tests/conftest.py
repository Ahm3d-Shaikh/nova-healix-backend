"""Shared fixtures: one container, one database, one app."""

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
from app.nasa.donki_client import DonkiClient
from app.nasa.horizons_client import HorizonsClient
from app.schemas.crew import Astronaut
from app.schemas.echo import EchoMessage, ItemRating, LonelinessRating

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


class FakeEchoCompanion:
    """Scripted stand-in for ECHO's Gemini: echoes replies and returns a preset rating."""

    model = "fake-model"

    def __init__(self) -> None:
        self.next_rating = rating()
        self.reply_calls: list[tuple[int, int]] = []  # (transcript length, replies left)
        self.fail_next: Exception | None = None  # raise this from the next reply()

    async def reply(self, astronaut: Astronaut, day: int, transcript: Sequence[EchoMessage], replies_left: int) -> str:
        self.reply_calls.append((len(transcript), replies_left))
        if self.fail_next is not None:
            exc, self.fail_next = self.fail_next, None
            raise exc
        return f"ECHO heard: {transcript[-1].content}"

    async def rate(self, astronaut: Astronaut, day: int, transcript: Sequence[EchoMessage]) -> LonelinessRating:
        return self.next_rating


class FakeReplier:
    """Scripted stand-in for Nova's Gemini replies."""

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
def echo_companion() -> FakeEchoCompanion:
    return FakeEchoCompanion()


@pytest.fixture
def replier() -> FakeReplier:
    return FakeReplier()


@pytest.fixture
def container(settings, db, echo_companion):
    """Nova on its rules, ECHO scripted, NASA feeds offline (the bundled snapshots)."""
    return asyncio.run(
        build_container(
            settings,
            db,
            donki=make_client(failing),
            horizons=make_horizons(failing),
            echo_companion=echo_companion,
            now_ms=NOW_MS,
        )
    )


@pytest.fixture
def api(settings, container):
    with TestClient(create_app(settings, container)) as client:
        yield client


@pytest.fixture
def hour(container) -> float:
    return container.clock.now_hour()

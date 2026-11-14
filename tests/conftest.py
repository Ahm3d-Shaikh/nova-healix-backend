import asyncio
from collections.abc import Sequence

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
from app.services.donki_client import DonkiClient
from app.services.horizons_client import HorizonsClient


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
    """Scripted stand-in for Gemini: echoes replies and returns a preset rating."""

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


@pytest.fixture
def settings() -> Settings:
    return Settings(supabase_url="", supabase_service_role_key="", gemini_api_key="")


@pytest.fixture
def companion() -> FakeCompanion:
    return FakeCompanion()


@pytest.fixture
def db() -> InMemoryDatabase:
    return InMemoryDatabase()


@pytest.fixture
def offline_container(settings, db, companion):
    """Container whose NASA calls always fail -> serves the bundled snapshots; in-memory database."""
    return asyncio.run(build_container(settings, make_client(failing), make_horizons(failing), db, companion))


@pytest.fixture
def api(settings, offline_container):
    with TestClient(create_app(settings, offline_container)) as client:
        yield client


def set_settings(api: TestClient, mission: str = "mars", deep_space_mode: bool = False, current_day: int = 5) -> None:
    """Change the saved mission settings (there is no public settings endpoint)."""
    service = api.app.state.container.mission_settings
    asyncio.run(
        service.update(MissionSettings(mission=mission, deep_space_mode=deep_space_mode, current_day=current_day))
    )

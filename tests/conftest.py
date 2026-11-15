import asyncio
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from app.container import build_container
from app.core.config import Settings
from app.db.memory import InMemoryDatabase
from app.main import create_app
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


class FakeReplier:
    """Scripted stand-in for Gemini."""

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
def replier() -> FakeReplier:
    return FakeReplier()


@pytest.fixture
def container(settings, db):
    return asyncio.run(build_container(settings, db, now_ms=NOW_MS))


@pytest.fixture
def api(settings, container):
    with TestClient(create_app(settings, container)) as client:
        yield client


@pytest.fixture
def hour(container) -> float:
    return container.clock.now_hour()

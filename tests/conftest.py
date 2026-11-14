import httpx
import pytest
from fastapi.testclient import TestClient

from app.container import build_container
from app.core.config import Settings
from app.main import create_app
from app.services.donki_client import DonkiClient


def make_client(handler) -> DonkiClient:
    return DonkiClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)), "https://donki.test", "KEY", backoff=0)


def failing(request: httpx.Request) -> httpx.Response:
    return httpx.Response(500)


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def offline_container(settings):
    """Container whose DONKI calls always fail -> serves the bundled snapshot."""
    return build_container(settings, make_client(failing))


@pytest.fixture
def api(settings, offline_container):
    with TestClient(create_app(settings, offline_container)) as client:
        yield client

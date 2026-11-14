"""Opt-in test against the REAL NASA DONKI API.

Run with:  NASA_API_KEY=<your key> pytest -m live
Skipped by default (DEMO_KEY allows only a handful of calls per hour).
"""

import asyncio
import os

import httpx
import pytest

from app.core.config import Settings
from app.models.enums import EventKind
from app.services.donki_client import DonkiClient, DonkiRateLimited

pytestmark = pytest.mark.live


@pytest.mark.skipif(not os.getenv("NASA_API_KEY"), reason="set NASA_API_KEY to run live DONKI tests")
def test_live_donki_storm_window():
    s = Settings()

    async def run():
        async with httpx.AsyncClient() as http:
            client = DonkiClient(http, s.donki_base_url, s.nasa_api_key)
            return await client.fetch_events(s.storm_window_start, s.storm_window_end)

    try:
        events = asyncio.run(run())
    except DonkiRateLimited:
        pytest.skip("NASA API key is rate limited right now")
    kinds = {e.kind for e in events}
    assert {EventKind.SEP, EventKind.FLARE, EventKind.CME, EventKind.GEOSTORM} <= kinds
    assert any(e.kind == EventKind.FLARE and e.class_type == "X2.2" for e in events)

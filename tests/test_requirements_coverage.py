"""Requirements document (FR / NFR / acceptance criteria) checks that are not covered elsewhere."""

import asyncio
from datetime import date
from pathlib import Path

import httpx
import pytest

from app.models.enums import DataSource
from app.rules import isolation
from app.services.space_weather_service import SpaceWeatherService
from tests.conftest import make_client


# --- FR-23: disclaimer -------------------------------------------------------------------------
def test_dashboard_carries_disclaimer(api):
    assert "not a medical device" in api.get("/api/dashboard").json()["disclaimer"]


def test_every_alert_has_a_source_and_ours_are_labelled_illustrative(api):
    seen = set()
    for day in range(1, 31):
        for crew in api.get("/api/dashboard", params={"day": day}).json()["crew"]:
            for card in crew["cards"]:
                for alert in card["alerts"]:
                    assert alert["source"], alert["rule"]
                    seen.add(alert["rule"])
                    if (
                        alert["rule"].split(".")[0] in {"R", "I", "D", "G", "MIRROR"}
                        and alert["rule"] != "R.cumulative_dose"
                    ):
                        assert "illustrative" in alert["source"], alert["rule"]
    assert {"R.sep_24h", "D.data_freshness", "G.cardio", "I.loneliness", "MIRROR.gap", "E.co2"} <= seen


# --- NFR-04: never colour alone ----------------------------------------------------------------
def test_cards_have_plain_text_headline(api):
    for crew in api.get("/api/dashboard", params={"day": 25}).json()["crew"]:
        for card in crew["cards"]:
            assert card["headline"]
    c = next(x for x in api.get("/api/dashboard", params={"day": 25}).json()["crew"] if x["astronaut"]["id"] == "C")
    assert "flagged for review" in next(k for k in c["cards"] if k["hazard"] == "G")["headline"]


# --- FR-10: loneliness trend ---------------------------------------------------------------------
def test_isolation_trend_function():
    assert isolation.trend([3, 3, 3])[0] == "insufficient_data"
    assert isolation.trend([3, 3, 3, 3, 3, 3])[0] == "stable"
    assert isolation.trend([3, 3, 3, 6, 6, 6]) == ("rising", 3.0)
    assert isolation.trend([7, 7, 7, 4, 4, 4]) == ("falling", -3.0)


def test_isolation_trend_in_dashboard(api):
    def trend(aid, day):
        crew = api.get("/api/dashboard", params={"day": day}).json()["crew"]
        card = next(k for k in next(c for c in crew if c["astronaut"]["id"] == aid)["cards"] if k["hazard"] == "I")
        return card["metrics"]["trend"]

    assert trend("C", 3) == "insufficient_data"
    assert trend("A", 25) == "stable"
    assert trend("C", 14) == "rising"


# --- NFR-01: works offline, even when the network hangs ---------------------------------------------------
def test_hanging_network_falls_back_quickly():
    async def hang(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(30)
        return httpx.Response(200, json=[])

    svc = SpaceWeatherService(
        make_client(hang),
        date(2024, 5, 8),
        date(2024, 5, 12),
        Path("app/data/donki_snapshot.json"),
        fetch_timeout_seconds=0.1,
    )
    data = asyncio.run(asyncio.wait_for(svc.get(), timeout=5))
    assert data.source == DataSource.SNAPSHOT
    assert data.reason == "live_unavailable"


@pytest.mark.parametrize("path", ["/api/dashboard", "/api/crew", "/api/alerts", "/api/distance"])
def test_core_endpoints_work_fully_offline(api, path):
    assert api.get(path).status_code == 200

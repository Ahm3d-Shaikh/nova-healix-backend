"""Requirements document (FR / NFR / acceptance criteria) checks that are not covered elsewhere."""

import asyncio
from datetime import date
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.container import build_container
from app.core.config import Settings
from app.main import create_app
from app.models.enums import DataSource
from app.models.isolation import IsolationResult
from app.rules import isolation
from app.rules.registry import THRESHOLD_REGISTRY
from app.services.space_weather_service import SpaceWeatherService
from app.services.store import JsonFileStore
from tests.conftest import failing, make_client

BODY = {"q1": 3, "q2": 3, "q3": 2}


# --- FR-23 / NFR-05: disclaimer and transparency --------------------------------------------
def test_meta_serves_disclaimer_data_provenance_thresholds_and_sources(api):
    meta = api.get("/api/meta").json()
    assert "not a medical device" in meta["disclaimer"]
    assert {r["status"] for r in meta["data"]} >= {"real", "simulated"}
    assert len(meta["sources"]) == 15
    assert all(s["url"].startswith("http") for s in meta["sources"])
    assert {t["provenance"] for t in meta["thresholds"]} == {"nasa", "csa", "published_method", "illustrative"}
    ours = [t for t in meta["thresholds"] if t["provenance"] == "illustrative"]
    assert ours
    assert all(t["source"] for t in meta["thresholds"])


def test_registry_covers_every_hazard():
    assert {t.hazard for t in THRESHOLD_REGISTRY} == {"R", "I", "D", "G", "E", "MIRROR"}


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


# --- FR-20 / TR-04: results are saved ---------------------------------------------------------------
def test_submissions_survive_a_restart(tmp_path):
    settings = Settings(submissions_dir=tmp_path)

    def start():
        return TestClient(create_app(settings, build_container(settings, make_client(failing))))

    with start() as api:
        api.post("/api/isolation/C?day=25", json=BODY)
        api.post("/api/mirror-gap/B?day=25", json={"self_rating": 8, "reaction_times_ms": [300, 320, 360, 380, 340]})
        assert (tmp_path / "isolation.json").exists()
    with start() as api:  # "restart"
        assert api.get("/api/isolation/C").json()["items"][-1]["source"] == "submitted"
        assert api.get("/api/mirror-gap/B").json()["items"][-1]["source"] == "submitted"
        assert len(api.get("/api/isolation/C").json()["items"]) == 31


def test_corrupt_store_file_is_quarantined_not_fatal(tmp_path):
    path = tmp_path / "isolation.json"
    path.write_text("{not json")
    store = JsonFileStore(path, IsolationResult)
    assert store.all("A") == []
    assert (tmp_path / "isolation.corrupt").exists()


# --- NFR-03: repeatable demo ------------------------------------------------------------------------------
def test_demo_reset_restores_start_state(api):
    api.post("/api/settings", json={"mission": "moon", "deep_space_mode": True, "current_day": 25})
    api.post("/api/isolation/C", json=BODY)
    api.post("/api/mirror-gap/B", json={"self_rating": 8, "reaction_times_ms": [300, 320, 360, 380, 340]})
    body = api.post("/api/demo/reset").json()
    assert (body["mission"], body["deep_space_mode"], body["current_day"]) == ("mars", False, 5)
    assert len(api.get("/api/isolation/C").json()["items"]) == 30
    assert len(api.get("/api/mirror-gap/B").json()["items"]) == 30


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


@pytest.mark.parametrize("path", ["/api/dashboard", "/api/timeline", "/api/space-weather", "/api/meta"])
def test_core_endpoints_work_fully_offline(api, path):
    assert api.get(path).status_code == 200

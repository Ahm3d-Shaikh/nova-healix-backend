"""NASA data: JPL Horizons (trajectory) and DONKI (storm events) feeding the mission."""

import asyncio
import json
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from app.container import build_container
from app.core.config import Settings
from app.db.memory import InMemoryDatabase
from app.main import create_app
from app.nasa.horizons_client import HorizonsError, parse_vectors
from app.nasa.models import SpaceWeatherEvent
from app.nasa.service import KM_PER_AU, NasaDataService, map_events
from app.nasa.space_weather_service import SpaceWeatherService
from app.repositories.cache import CacheRepository
from tests.conftest import NOW_MS, failing, make_client, make_horizons

# Mars at 2.2 AU from Earth on the arrival day (a one-row Horizons CSV vector table).
RG_KM = 2.2 * KM_PER_AU
RESULT = f"""\
 JDTDB, Calendar Date (TDB), X, Y, Z, VX, VY, VZ, LT, RG, RR,
$$SOE
2461600.500000000, A.D. 2027-Jul-15 00:00:00.0000,  2.98E+08, -4.49E+07, -6.65E+06,  5.5E-01,  4.7E+01,  8.6E-02,  \
{RG_KM / 299792.458},  {RG_KM}, -6.5,
$$EOE
"""


def horizons_ok(request: httpx.Request) -> httpx.Response:
    assert request.url.params["COMMAND"] == "'499'" and request.url.params["CENTER"] == "'500@399'"
    return httpx.Response(200, json={"result": RESULT})


def snapshot_events() -> list[SpaceWeatherEvent]:
    raw = json.loads(Settings().donki_snapshot_path.read_text())
    return [SpaceWeatherEvent.model_validate(e) for e in raw["events"]]


def nasa(container, db, horizons_handler, donki_handler=failing) -> NasaDataService:
    cache = CacheRepository(db)
    s = Settings()
    return NasaDataService(
        weather=SpaceWeatherService(
            make_client(donki_handler), s.storm_window_start, s.storm_window_end, s.donki_snapshot_path, cache=cache
        ),
        horizons=make_horizons(horizons_handler),
        cache=cache,
        data=container.data,
        trajectory=container.trajectory,
        clock=container.clock,
    )


def test_parse_vectors():
    samples = parse_vectors(RESULT)
    assert len(samples) == 1 and samples[0].time == datetime(2027, 7, 15, tzinfo=UTC)
    assert samples[0].distance_km == pytest.approx(RG_KM)


def test_parse_vectors_rejects_missing_table():
    with pytest.raises(HorizonsError):
        parse_vectors("No ephemeris for target")


def test_storm_events_are_mapped_onto_mission_day_97():
    events = map_events(snapshot_events())
    assert len(events) == 18 and all(e.source == "NASA DONKI" for e in events)
    seps = [e for e in events if e.kind == "spe"]
    assert len(seps) == 8 and seps[0].start == 2307.0  # the first real SEP starts the mission's own D97 storm (03:00)
    assert {e.label.split(" ")[0] for e in events if e.kind == "anomaly"} >= {"X2.2", "Geomagnetic"}
    assert all(e.hazards and e.crew_ids == [] for e in events)
    assert map_events([]) == []


def test_horizons_arrival_distance_sets_the_trajectory_and_is_cached(settings):
    db = InMemoryDatabase()
    container = asyncio.run(build_container(settings, db, now_ms=NOW_MS))
    before = list(container.trajectory.au)
    version = container.data.version
    asyncio.run(nasa(container, db, horizons_ok).refresh())
    au = container.trajectory.au
    assert (
        container.trajectory.source == "NASA JPL Horizons"
        and container.mission_config().trajectory_source == "NASA JPL Horizons"
    )
    assert len(au) == 261 and au[-1] == pytest.approx(2.2, rel=1e-6) and 0.004 < au[0] < 0.01
    assert au != before and au == sorted(au)  # grows smoothly outward
    assert container.data.version > version  # cached analyses are invalidated
    # a fresh process whose Horizons call fails reuses the saved distance
    second = asyncio.run(build_container(settings, db, now_ms=NOW_MS))
    asyncio.run(nasa(second, db, failing).refresh())
    assert second.trajectory.au[-1] == pytest.approx(2.2, rel=1e-6)


def test_horizons_failure_keeps_the_model_trajectory(settings):
    db = InMemoryDatabase()
    container = asyncio.run(build_container(settings, db, now_ms=NOW_MS))
    before = list(container.trajectory.au)
    asyncio.run(nasa(container, db, failing).refresh())
    assert container.trajectory.au == before and container.trajectory.source == "model"
    assert (
        asyncio.run(nasa(container, db, lambda r: httpx.Response(200, json={"error": "no such target"})).refresh())
        is None
    )


def test_storm_events_reach_the_api_and_the_signal_delay_follows_the_trajectory(settings):
    db = InMemoryDatabase()
    container = asyncio.run(build_container(settings, db, now_ms=NOW_MS))
    asyncio.run(nasa(container, db, horizons_ok).refresh())  # DONKI fails -> bundled snapshot of the real storm
    with TestClient(create_app(settings, container)) as api:
        events = api.get("/api/mission/events").json()
        donki = [e for e in events if e.get("source") == "NASA DONKI"]
        assert len(donki) == 18 and events[0]["id"] == "tcm-1" and "source" not in events[0]  # built-in events first
        tl = api.get("/api/crew/ahmad/timeline", params={"from": 2290, "to": 2330}).json()
        assert any(e["id"].startswith("donki-") for e in tl)
        # the radiation insight still points at the mission's own storm, not at a NASA event
        rad = next(i for i in api.get("/api/insights").json() if i["id"] == "rad-outlier:sabaina")
        assert rad["evidence"][-1]["value"] == "Solar particle event, storm shelter"
        m = api.get("/api/mission").json()
        assert m["trajectorySource"] == "NASA JPL Horizons"
        hz = api.get("/api/assessment/hazards").json()
        delay = next(h for h in hz if h["crewId"] == "hashir" and h["hazard"] == "distance")["headline"]
        assert "delay" in delay  # derived from the Horizons-based trajectory

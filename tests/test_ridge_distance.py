import asyncio
from datetime import date

import httpx
import pytest

from app.core.config import Settings
from app.db.memory import InMemoryDatabase
from app.models.enums import DataSource, Mission
from app.repositories.cache import CacheRepository
from app.services.distance_service import DistanceService
from app.services.horizons_client import HorizonsError, parse_vectors
from tests.conftest import failing, make_horizons, set_settings

RESULT = """\
*******************************************************************************
 JDTDB, Calendar Date (TDB), X, Y, Z, VX, VY, VZ, LT, RG, RR,
$$SOE
2460420.500000000, A.D. 2024-Apr-20 00:00:00.0000,  2.98E+08, -4.49E+07, -6.65E+06,  5.5E-01,  4.7E+01,  8.6E-02,  \
1.007062394658004E+03,  3.019097106538891E+08, -6.549699518931235E+00,
2460421.500000000, A.D. 2024-Apr-21 00:00:00.0000,  2.98E+08, -4.08E+07, -6.64E+06, -1.0E-01,  4.7E+01,  9.5E-02,  \
1.005175605492395E+03,  3.013440654922034E+08, -6.543966383879918E+00,
$$EOE
"""


def horizons_ok(request: httpx.Request) -> httpx.Response:
    assert request.url.params["COMMAND"] == "'499'" and request.url.params["CENTER"] == "'500@399'"
    return httpx.Response(200, json={"result": RESULT, "signature": {}})


def service(handler, db=None) -> DistanceService:
    s = Settings()
    start, end = s.mission_window
    return DistanceService(
        make_horizons(handler), start, end, s.horizons_snapshot_path, CacheRepository(db or InMemoryDatabase())
    )


def test_parse_vectors():
    samples = parse_vectors(RESULT)
    assert len(samples) == 2
    assert samples[0].time.isoformat() == "2024-04-20T00:00:00+00:00"
    assert round(samples[0].light_time_s) == 1007 and round(samples[0].distance_km) == 301909711
    assert samples[1].range_rate_km_s < 0


def test_parse_vectors_rejects_missing_table():
    with pytest.raises(HorizonsError):
        parse_vectors("No ephemeris for target")


def test_live_fetch_then_db_cache_after_restart():
    db = InMemoryDatabase()
    live = asyncio.run(service(horizons_ok, db).get(Mission.MARS))
    assert live.source == DataSource.LIVE and live.target_name == "Mars" and len(live.samples) == 2
    # A fresh process whose Horizons call fails falls back to the copy saved in the database.
    cached = asyncio.run(service(failing, db).get(Mission.MARS))
    assert cached.source == DataSource.CACHED and cached.reason == "live_unavailable"
    assert cached.samples == live.samples


def test_snapshot_fallback_covers_every_mission():
    svc = service(failing)
    for mission in Mission:
        data = asyncio.run(svc.get(mission))
        assert data.source == DataSource.SNAPSHOT and len(data.samples) == 31
    assert asyncio.run(svc.get(Mission.MARS, deep_space_mode=True)).reason == "deep_space_mode"


def test_horizons_error_payload_falls_back():
    data = asyncio.run(service(lambda r: httpx.Response(200, json={"error": "bad target"})).get(Mission.MOON))
    assert data.source == DataSource.SNAPSHOT


def test_sample_lookup_uses_latest_before_moment():
    data = asyncio.run(service(failing).get(Mission.MOON))
    from datetime import UTC, datetime

    s = data.at(datetime(2024, 5, 1, 12, tzinfo=UTC))
    assert s is not None and s.time.date() == date(2024, 5, 1)


def test_distance_endpoint_and_card(api):
    body = api.get("/api/distance").json()
    assert body["mission"] == "mars" and body["source"] == "snapshot" and len(body["days"]) == 30
    assert all(180 < d["light_time_s"] < 1400 for d in body["days"])  # Mars: 3-22 min

    set_settings(api, "moon", False, 5)
    dash = api.get("/api/dashboard").json()
    assert dash["distance"]["target_name"] == "Moon" and dash["distance"]["source"] == "snapshot"
    card = next(c for c in dash["crew"][0]["cards"] if c["hazard"] == "D")
    m = card["metrics"]
    assert 356_000 < m["distance_km"] < 407_000 and 1.1 < m["one_way_light_time_s"] < 1.4
    assert m["round_trip_light_time_s"] == pytest.approx(2 * m["one_way_light_time_s"], abs=0.002)
    delay = next(a for a in card["alerts"] if a["rule"] == "D.comms_delay")
    assert delay["level"] == "green" and "Moon" in delay["what"]


def test_mars_delay_is_amber(api):
    card = next(c for c in api.get("/api/dashboard").json()["crew"][0]["cards"] if c["hazard"] == "D")
    delay = next(a for a in card["alerts"] if a["rule"] == "D.comms_delay")
    assert delay["level"] == "amber" and "AU" in delay["what"]

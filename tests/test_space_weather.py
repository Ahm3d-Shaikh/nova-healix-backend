import asyncio
import json
from pathlib import Path

import httpx

from app.models.enums import DataSource, EventKind
from app.services import donki_parsers as p
from app.services.space_weather_service import SpaceWeatherService
from datetime import date

from tests.conftest import make_client, failing

SEP = [{"sepID": "S1", "eventTime": "2024-05-09T13:59Z", "instruments": [{"displayName": "ACE"}]}]
CME = [{"activityID": "C1", "startTime": "2024-05-09T10:00Z",
        "cmeAnalyses": [{"isMostAccurate": True, "speed": 1200.0}]}]
GST = [{"gstID": "G1", "startTime": "2024-05-10T15:00Z", "allKpIndex": [{"kpIndex": 9.0}]}]
NOTES = [{"messageType": "FLR", "messageID": "N1", "messageIssueTime": "2024-05-09T12:10Z",
          "messageBody": "## Message Type: Space Weather Notification - X2.2 Flare\n##"}]


def donki(flr_ok=True):
    def handler(request: httpx.Request) -> httpx.Response:
        feed = request.url.path.rsplit("/", 1)[-1]
        if feed == "FLR":
            return httpx.Response(200, json=[{"flrID": "F1", "peakTime": "2024-05-09T12:03Z", "classType": "X2.2"}]) \
                if flr_ok else httpx.Response(404)
        return httpx.Response(200, json={"SEP": SEP, "CME": CME, "GST": GST, "notifications": NOTES}[feed])
    return handler


def service(handler, tmp_path=None):
    return SpaceWeatherService(make_client(handler), date(2024, 5, 8), date(2024, 5, 12),
                               Path("app/data/donki_snapshot.json"), cache_ttl_seconds=3600)


def test_parsers_normalize_fields():
    assert p.parse_sep(SEP)[0].kind == EventKind.SEP
    assert p.parse_cme(CME)[0].speed_km_s == 1200.0
    assert p.parse_gst(GST)[0].kp_index == 9.0
    assert p.parse_flares_from_notifications(NOTES)[0].class_type == "X2.2"


def test_live_fetch_and_cache():
    calls = []
    inner = donki()
    def counting(req):
        calls.append(req.url.path)
        return inner(req)
    svc = service(counting)
    first = asyncio.run(svc.get())
    n = len(calls)
    second = asyncio.run(svc.get())
    assert first.source == second.source == DataSource.LIVE and len(calls) == n  # second call hit cache
    assert {e.kind for e in first.events} >= {EventKind.SEP, EventKind.FLARE, EventKind.CME}


def test_flare_endpoint_down_falls_back_to_notifications():
    data = asyncio.run(service(donki(flr_ok=False)).get())
    assert data.source == DataSource.LIVE
    assert [e.class_type for e in data.events if e.kind == EventKind.FLARE] == ["X2.2"]


def test_failure_serves_snapshot():
    data = asyncio.run(service(failing).get())
    assert data.source == DataSource.SNAPSHOT and data.reason == "live_unavailable" and data.events


def test_deep_space_mode_prefers_cache_then_snapshot():
    svc = service(donki())
    assert asyncio.run(svc.get(deep_space_mode=True)).source == DataSource.SNAPSHOT
    asyncio.run(svc.get())
    deep = asyncio.run(svc.get(deep_space_mode=True))
    assert deep.source == DataSource.CACHED and deep.reason == "deep_space_mode"


def test_snapshot_file_is_valid():
    raw = json.loads(Path("app/data/donki_snapshot.json").read_text())
    assert any(e["kind"] == "sep" for e in raw["events"])

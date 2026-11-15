import asyncio
import json
from datetime import date
from pathlib import Path

import httpx

from app.nasa import donki_parsers as p
from app.nasa.models import DataSource, EventKind
from app.nasa.space_weather_service import SpaceWeatherService
from tests.conftest import failing, make_client

SEP = [{"sepID": "S1", "eventTime": "2024-05-09T13:59Z", "instruments": [{"displayName": "ACE"}]}]
CME = [
    {
        "activityID": "C1",
        "startTime": "2024-05-09T10:00Z",
        "cmeAnalyses": [{"isMostAccurate": True, "speed": 1200.0}],
    }
]
GST = [{"gstID": "G1", "startTime": "2024-05-10T15:00Z", "allKpIndex": [{"kpIndex": 9.0}]}]
NOTES = [
    {
        "messageType": "FLR",
        "messageID": "N1",
        "messageIssueTime": "2024-05-09T12:10Z",
        "messageBody": "## Message Type: Space Weather Notification - X2.2 Flare\n##",
    }
]


def donki(flr_ok=True):
    def handler(request: httpx.Request) -> httpx.Response:
        feed = request.url.path.rsplit("/", 1)[-1]
        if feed == "FLR":
            return (
                httpx.Response(200, json=[{"flrID": "F1", "peakTime": "2024-05-09T12:03Z", "classType": "X2.2"}])
                if flr_ok
                else httpx.Response(404)
            )
        return httpx.Response(200, json={"SEP": SEP, "CME": CME, "GST": GST, "notifications": NOTES}[feed])

    return handler


class FakeClock:
    """Injectable monotonic clock so tests can 'wait' without sleeping."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def service(handler, clock=None, client=None):
    return SpaceWeatherService(
        client or make_client(handler),
        date(2024, 5, 8),
        date(2024, 5, 12),
        Path("app/data/donki_snapshot.json"),
        cache_ttl_seconds=3600,
        **({"clock": clock} if clock else {}),
    )


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


# --- Real DONKI payloads (saved May 2024 responses) -----------------------------
FIXTURES = Path("tests/fixtures/donki")


def replay(flr_status=404, status_override=None, calls=None):
    """Serve the saved real responses as if they came from api.nasa.gov."""

    def handler(request: httpx.Request) -> httpx.Response:
        feed = request.url.path.rsplit("/", 1)[-1]
        if calls is not None:
            calls.append(feed)
        if status_override:
            return httpx.Response(status_override, headers={"x-ratelimit-remaining": "0"}, json={})
        if feed == "FLR":
            return httpx.Response(flr_status)
        return httpx.Response(
            200, headers={"x-ratelimit-remaining": "7"}, content=(FIXTURES / f"{feed}.json").read_bytes()
        )

    return handler


def test_real_payloads_match_bundled_snapshot():
    client = make_client(replay())
    svc = service(None, client=client)
    live = asyncio.run(svc.get())
    snap = svc.load_snapshot()
    assert live.source == DataSource.LIVE
    assert [e.id for e in live.events] == [e.id for e in snap.events]
    assert client.rate_limit_remaining == 7
    flares = {e.class_type for e in live.events if e.kind == EventKind.FLARE}
    assert {"X2.2", "X5.8", "X3.9"} <= flares


def test_rate_limit_is_reported_and_not_hammered():
    from app.nasa.models import DataSource as DS

    calls = []
    svc = service(replay(status_override=429, calls=calls))
    first = asyncio.run(svc.get())
    n = len(calls)
    second = asyncio.run(svc.get())
    assert first.source == second.source == DS.SNAPSHOT and first.reason == "rate_limited"
    assert len(calls) == n  # backed off: no new network calls
    assert n <= 5  # a 429 is never retried


def test_rate_limit_after_success_serves_cache():
    clock = FakeClock()
    throttled = {"on": False}
    ok = replay()
    limited = replay(status_override=429)
    svc = service(lambda req: limited(req) if throttled["on"] else ok(req), clock=clock)
    assert asyncio.run(svc.get()).source == DataSource.LIVE
    clock.advance(7200)  # cache expires
    throttled["on"] = True
    data = asyncio.run(svc.get())
    assert data.source == DataSource.CACHED
    assert data.reason == "rate_limited"


def test_backoff_ends_and_live_data_returns():
    clock = FakeClock()
    throttled = {"on": True}
    ok = replay()
    limited = replay(status_override=429)
    svc = service(lambda req: limited(req) if throttled["on"] else ok(req), clock=clock)
    assert asyncio.run(svc.get()).source == DataSource.SNAPSHOT
    throttled["on"] = False
    assert asyncio.run(svc.get()).source == DataSource.SNAPSHOT  # still backing off
    clock.advance(1000)  # past the 15-minute rate-limit wait
    assert asyncio.run(svc.get()).source == DataSource.LIVE


def test_transient_5xx_is_retried_then_succeeds():
    attempts = {"SEP": 0}
    inner = replay()

    def flaky(req):
        if req.url.path.endswith("/SEP") and attempts["SEP"] < 2:
            attempts["SEP"] += 1
            return httpx.Response(503)
        return inner(req)

    data = asyncio.run(service(flaky).get())
    assert data.source == DataSource.LIVE and attempts["SEP"] == 2


def test_rate_limit_error_object_with_http_200_falls_back():
    def handler(req):
        return httpx.Response(200, json={"error": {"code": "OVER_RATE_LIMIT"}})

    data = asyncio.run(service(handler).get())
    assert data.source == DataSource.SNAPSHOT


def test_network_error_falls_back():
    def boom(req):
        raise httpx.ConnectError("no network")

    assert asyncio.run(service(boom).get()).source == DataSource.SNAPSHOT

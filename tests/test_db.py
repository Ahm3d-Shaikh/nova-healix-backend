import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.container import build_container
from app.db.base import DatabaseError
from app.db.memory import InMemoryDatabase
from app.db.supabase import SupabaseDatabase
from app.main import create_app
from tests.conftest import NOW_MS


def supabase(handler) -> SupabaseDatabase:
    return SupabaseDatabase(httpx.AsyncClient(transport=httpx.MockTransport(handler)), "https://x.supabase.co/", "KEY")


def test_supabase_select_builds_postgrest_query():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[{"id": "A"}])

    rows = asyncio.run(
        supabase(handler).table("astronauts").select(eq={"id": "A", "flag": True}, order="day", desc=True, limit=5)
    )
    req = seen[0]
    assert rows == [{"id": "A"}]
    assert req.url.path == "/rest/v1/astronauts"
    assert dict(req.url.params) == {"select": "*", "id": "eq.A", "flag": "eq.true", "order": "day.desc", "limit": "5"}
    assert req.headers["apikey"] == "KEY" and req.headers["authorization"] == "Bearer KEY"


def test_supabase_writes_use_prefer_headers():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method in ("DELETE",) or (request.method == "POST" and "on_conflict" in request.url.params):
            return httpx.Response(204)
        return httpx.Response(201, json=[json.loads(request.content)])

    table = supabase(handler).table("t")
    assert asyncio.run(table.insert({"id": 1})) == {"id": 1}
    asyncio.run(table.upsert([{"id": 1}], on_conflict="id"))
    asyncio.run(table.update({"id": 1}, {"x": 2}))
    asyncio.run(table.delete({"id": 1}))
    assert asyncio.run(table.upsert([], on_conflict="id")) is None  # no request for nothing
    insert, upsert, update, delete = seen
    assert insert.headers["prefer"] == "return=representation"
    assert upsert.headers["prefer"] == "resolution=merge-duplicates,return=minimal"
    assert upsert.url.params["on_conflict"] == "id"
    assert update.method == "PATCH" and update.url.params["id"] == "eq.1"
    assert delete.method == "DELETE" and delete.url.params["id"] == "eq.1"


def test_supabase_refuses_to_delete_everything():
    with pytest.raises(DatabaseError):
        asyncio.run(supabase(lambda r: httpx.Response(204)).table("t").delete({}))


@pytest.mark.parametrize(
    "handler",
    [
        lambda r: httpx.Response(401, text="bad key"),
        lambda r: httpx.Response(200, text="not json"),
        lambda r: httpx.Response(200, json={"not": "a list"}),
        lambda r: (_ for _ in ()).throw(httpx.ConnectError("down")),
    ],
)
def test_supabase_failures_raise_database_error(handler):
    with pytest.raises(DatabaseError):
        asyncio.run(supabase(handler).table("t").select())


def test_memory_upsert_merges_on_composite_key():
    t = InMemoryDatabase().table("t")
    asyncio.run(t.upsert([{"a": 1, "b": 1, "v": 1}, {"a": 1, "b": 2, "v": 2}], on_conflict="a,b"))
    asyncio.run(t.upsert([{"a": 1, "b": 1, "v": 9}], on_conflict="a,b"))
    assert asyncio.run(t.select(order="v", desc=True)) == [{"a": 1, "b": 1, "v": 9}, {"a": 1, "b": 2, "v": 2}]
    asyncio.run(t.delete({"a": 1, "b": 2}))
    assert asyncio.run(t.select()) == [{"a": 1, "b": 1, "v": 9}]


def build(settings, db, now_ms=NOW_MS):
    return asyncio.run(build_container(settings, db, now_ms=now_ms))


def test_everything_written_survives_a_restart(settings):
    """Check-ins, questionnaires, notes, safety flags, messages, log and resolutions are all reloaded."""
    db = InMemoryDatabase()
    with TestClient(create_app(settings, build(settings, db))) as api:
        api.post(
            "/api/crew/hashir/checkins", json={"mood": 1, "sleepQuality": 2, "energy": 3, "symptoms": ["headache"]}
        )
        wb = next(x for x in api.get("/api/crew/ahmad/assignments").json() if x["questionnaireId"] == "wellbeing")
        api.put(f"/api/assignments/{wb['id']}/progress", json={"answers": {"w1": 3}, "currentIndex": 1})
        api.post(f"/api/assignments/{wb['id']}/submit", json={"answers": {"w1": 5, "w2": 1, "w3": 1, "w4": 1, "w5": 5}})
        api.post("/api/crew/hannan/shared-notes", json={"text": "Could we talk this week?"})
        api.post(
            "/api/crew/ahmad/companion/reply",
            json={
                "text": "I want to die",
                "history": [],
                "state": {"pendingSafetyCheck": False, "awaitingCheckIn": False},
            },
        )
        api.post("/api/crew/ahmad/messages", json={"text": "I'm here", "insightId": "sleep-debt:ahmad"})
        api.post("/api/insights/sleep-debt:ahmad/resolve", json={"crewId": "ahmad", "note": "ok", "severity": "watch"})
        api.post(
            "/api/insights/isolation-stress:hannan/resolve", json={"crewId": "hannan", "note": "x", "severity": "alert"}
        )
        api.post("/api/insights/isolation-stress:hannan/reopen", json={"crewId": "hannan"})
        before = api.get("/api/insights").json()

    with TestClient(create_app(settings, build(settings, db))) as api:
        assert api.get("/api/insights").json() == before
        assert api.get("/api/crew/hashir/checkins", params={"from": 3360, "to": 3400}).json()[-1]["mood"] == 1
        done = api.get(f"/api/assignments/{wb['id']}").json()
        assert done["status"] == "done" and done["score"] == 100
        assert api.get("/api/crew/ahmad/metrics/stress", params={"from": 3300, "to": 3398}).json()[-1]["v"] == 100
        assert len(api.get("/api/crew/ahmad/messages").json()) == 1
        assert [e["kind"] for e in api.get("/api/actions").json()] == ["message", "resolve", "resolve", "reopen"]


def test_launch_epoch_is_saved_and_reused_across_days(settings):
    db = InMemoryDatabase()
    first = build(settings, db)
    day_later = NOW_MS + 24 * 3_600_000
    second = build(settings, db, now_ms=day_later)
    assert second.clock.launch_epoch_ms == first.clock.launch_epoch_ms  # stored hours stay aligned
    assert second.clock.current_day() == 143
    # far outside the generated data: re-anchor to day 142 again
    third = build(settings, db, now_ms=NOW_MS + 30 * 24 * 3_600_000)
    assert third.clock.launch_epoch_ms != first.clock.launch_epoch_ms and third.clock.current_day() == 142


def test_explicit_launch_epoch_wins(settings):
    s = settings.model_copy(update={"launch_epoch_ms": 1_000_000_000_000})
    assert build(s, InMemoryDatabase()).clock.launch_epoch_ms == 1_000_000_000_000


def test_unreachable_database_still_serves_the_simulation_and_503s_writes(settings):
    container = build(settings, supabase(lambda r: httpx.Response(503, text="down")))
    assert container.database == "supabase"
    with TestClient(create_app(settings, container)) as api:
        assert api.get("/api/assessment/hazards").status_code == 200  # simulated defaults
        resp = api.post("/api/crew/hashir/checkins", json={"mood": 3, "sleepQuality": 3, "energy": 3, "symptoms": []})
        assert resp.status_code == 503 and "Database" in resp.json()["detail"]
        # a failed write never leaves memory ahead of the database: today's check-in is still the generated one
        today = next(c for c in container.data.check_ins("hashir") if c.day == 142)
        assert today.at < container.clock.quarter_hour() and today.mood != 3


def test_safety_flag_survives_a_database_outage(settings):
    """A person at risk must still raise the alert even if the database is down: it is held in memory."""
    container = build(settings, supabase(lambda r: httpx.Response(503, text="down")))
    with TestClient(create_app(settings, container)) as api:
        r = api.post(
            "/api/crew/ahmad/companion/reply",
            json={
                "text": "I want to die",
                "history": [],
                "state": {"pendingSafetyCheck": False, "awaitingCheckIn": False},
            },
        )
        assert r.status_code == 200 and r.json()["safety"]["category"] == "self-harm"
        assert api.get("/api/insights").json()[0]["id"].startswith("safety:")

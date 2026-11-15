import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.db.base import DatabaseError
from app.db.memory import InMemoryDatabase
from app.db.supabase import SupabaseDatabase
from app.repositories.crew import CrewRepository
from app.ridge_container import build_ridge_container as build_container
from tests.conftest import FakeCompanion, combined_app, failing, make_client, make_horizons, set_settings


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
        if request.method == "POST" and "on_conflict" in request.url.params:
            return httpx.Response(201)
        return httpx.Response(201, json=[json.loads(request.content)])

    table = supabase(handler).table("t")
    assert asyncio.run(table.insert({"id": 1})) == {"id": 1}
    asyncio.run(table.upsert([{"id": 1}], on_conflict="id"))
    asyncio.run(table.update({"id": 1}, {"x": 2}))
    assert asyncio.run(table.upsert([], on_conflict="id")) is None  # no request for nothing
    insert, upsert, update = seen
    assert insert.headers["prefer"] == "return=representation"
    assert upsert.headers["prefer"] == "resolution=merge-duplicates,return=minimal"
    assert upsert.url.params["on_conflict"] == "id"
    assert update.method == "PATCH" and update.url.params["id"] == "eq.1"


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


def build(settings, db):
    return asyncio.run(build_container(settings, make_client(failing), make_horizons(failing), db, FakeCompanion()))


def test_crew_is_seeded_once_and_reloaded(settings):
    db = InMemoryDatabase()
    first = build(settings, db)
    stored = asyncio.run(CrewRepository(db).records())
    assert set(stored) == {"A", "B", "C"} and len(stored["A"]) == 30
    assert stored["B"] == first.crew.records("B")  # float columns round-trip exactly
    second = build(settings, db)
    assert second.crew.records("C") == first.crew.records("C")


def test_state_survives_a_restart(settings):
    db = InMemoryDatabase()
    with TestClient(combined_app(settings, build(settings, db), db)) as api:
        set_settings(api, "moon", True, 12)
        start = api.post("/api/isolation/A/sessions").json()
        sid = start["session"]["id"]
        for i in range(3):
            api.post(f"/api/isolation/A/sessions/{sid}/messages", json={"content": f"reply {i}"})
        api.post(f"/api/isolation/A/sessions/{sid}/complete")
    with TestClient(combined_app(settings, build(settings, db), db)) as api:
        s = api.get("/api/dashboard").json()["settings"]
        assert (s["mission"], s["deep_space_mode"], s["current_day"]) == ("moon", True, 12)
        detail = api.get(f"/api/isolation/A/sessions/{sid}").json()
        assert len(detail["messages"]) == 7 and detail["assessment"]["mission_day"] == 12


def test_unreachable_database_falls_back_for_crew_and_returns_503_for_writes(settings):
    db = supabase(lambda r: httpx.Response(503, text="down"))
    container = build(settings, db)
    assert container.database == "supabase" and len(container.crew.records("A")) == 30
    with TestClient(combined_app(settings, container, db)) as api:
        resp = api.get("/api/dashboard")
        assert resp.status_code == 503 and "Database" in resp.json()["detail"]


def test_incomplete_db_records_use_simulated_data(settings):
    db = InMemoryDatabase()
    build(settings, db)
    db.table("daily_records")._rows = [r for r in db.table("daily_records")._rows if r["astronaut_id"] != "B"]
    asyncio.run(db.table("astronauts").insert({"id": "X", "name": "X", "role": "r", "story": "s"}))
    container = build(settings, db)
    assert len(container.crew.records("B")) == 30
    assert [a.astronaut.id for a in asyncio.run(container.crew.summaries(5))] == ["A", "B", "C"]  # X skipped

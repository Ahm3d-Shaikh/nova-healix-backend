import asyncio

from tests.conftest import set_settings


def test_health_and_root(api):
    health = api.get("/health").json()
    # One superset for both APIs: Nova v2 (companion, missionHour) and RIDGE (database, ai_checkin).
    assert {k: health[k] for k in ("status", "version", "database", "ai_checkin", "companion")} == {
        "status": "ok",
        "version": "3.0.0",
        "database": "memory",
        "ai_checkin": True,
        "companion": "rules",
    }
    assert isinstance(health["missionHour"], float)
    assert "not a medical device" in api.get("/").json()["disclaimer"]


def test_crew_list_and_detail(api):
    crew = api.get("/api/ridge/crew", params={"day": 25}).json()
    assert [c["astronaut"]["id"] for c in crew] == ["A", "B", "C"]
    detail = api.get("/api/ridge/crew/c", params={"day": 25}).json()
    assert len(detail["records"]) == 25 and len(detail["cards"]) == 6
    flagged = {a["hazard"] for a in detail["alerts"]}
    assert {"G", "I"} <= flagged
    for a in detail["alerts"]:
        assert all(a[k] for k in ("what", "why", "action", "source"))


def test_unknown_astronaut_404(api):
    assert api.get("/api/ridge/crew/Z").status_code == 404
    assert api.get("/api/isolation/Z").status_code == 404


def test_alerts_sorted_worst_first(api):
    alerts = api.get("/api/alerts", params={"day": 25}).json()
    ranks = [a["level"] for a in alerts]
    assert ranks == sorted(ranks, key=lambda lv: lv != "red")
    assert {a["astronaut_id"] for a in alerts} == {"A", "B", "C"}  # A only has the Distance (snapshot) alert


def test_saved_settings_drive_default_day_and_mission(api):
    set_settings(api, mission="moon", deep_space_mode=True, current_day=12)
    body = api.get("/api/dashboard").json()
    assert body["day"] == 12 and body["settings"]["comms_delay"] == "≈1.3 s"
    assert body["settings"]["deep_space_mode"] is True
    assert api.get("/api/ridge/crew").json()[0]["day"] == 12


def test_removed_endpoints_are_gone(api):
    for path in ("/api/space-weather", "/api/settings", "/api/timeline", "/api/mirror-gap/A"):
        assert api.get(path).status_code == 404, path


def test_out_of_range_day_is_rejected(api):
    for path in ("/api/ridge/crew", "/api/dashboard", "/api/alerts", "/api/ridge/crew/A"):
        resp = api.get(path, params={"day": 31})
        assert resp.status_code == 422, path
        assert "outside 1-30" in resp.json()["detail"]
    assert api.get("/api/ridge/crew", params={"day": 0}).status_code == 422
    assert api.post("/api/isolation/A/sessions?day=99").status_code == 422


def test_error_bodies_are_json_detail(api):
    resp = api.get("/api/ridge/crew/Z")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Unknown astronaut 'Z'"}


def test_responses_carry_request_id_and_security_headers(api):
    resp = api.get("/health")
    assert len(resp.headers["x-request-id"]) == 12
    assert float(resp.headers["x-process-time-ms"]) >= 0
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert api.get("/health").headers["x-request-id"] != resp.headers["x-request-id"]


def test_large_responses_are_gzipped(api):
    resp = api.get("/api/dashboard", headers={"accept-encoding": "gzip"})
    assert resp.headers["content-encoding"] == "gzip"


def test_cors_allows_only_configured_origin(api):
    ok = api.get("/health", headers={"origin": "http://localhost:4200"})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:4200"
    other = api.get("/health", headers={"origin": "http://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_openapi_schema_exposes_typed_card_metrics(api):
    schema = api.get("/openapi.json").json()["components"]["schemas"]
    assert {"RadiationMetrics", "GravityMetrics", "MirrorMetrics"} <= set(schema)
    assert schema["CardStatus"]["properties"]["metrics"]["discriminator"]["propertyName"] == "kind"


def test_blank_nasa_key_falls_back_to_demo_key():
    from app.core.config import Settings

    assert Settings(nasa_api_key="   ").nasa_api_key == "DEMO_KEY"
    assert Settings(nasa_api_key=" abc ").nasa_api_key == "abc"


def test_settings_reject_out_of_range_day_instead_of_clamping(api):
    import pytest

    from app.core.errors import InvalidDayError
    from app.models.settings import MissionSettings

    service = api.app.state.ridge.mission_settings
    with pytest.raises(InvalidDayError, match="outside 1-30"):
        asyncio.run(service.update(MissionSettings(mission="mars", deep_space_mode=False, current_day=99)))
    assert api.get("/api/dashboard").json()["settings"]["current_day"] == 5  # unchanged

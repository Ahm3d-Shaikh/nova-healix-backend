def test_health_and_root(api):
    assert api.get("/health").json() == {"status": "healthy", "version": "2.0.0"}
    assert "not a medical device" in api.get("/").json()["disclaimer"]


def test_space_weather_snapshot_fallback(api):
    body = api.get("/api/space-weather").json()
    assert body["source"] == "snapshot" and body["reason"] == "live_unavailable"
    assert any(e["kind"] == "sep" and e["mission_day"] == 20 for e in body["events"])


def test_crew_list_and_detail(api):
    crew = api.get("/api/crew", params={"day": 25}).json()
    assert [c["astronaut"]["id"] for c in crew] == ["A", "B", "C"]
    detail = api.get("/api/crew/c", params={"day": 25}).json()
    assert len(detail["records"]) == 25 and len(detail["cards"]) == 6
    flagged = {a["hazard"] for a in detail["alerts"]}
    assert {"G", "I"} <= flagged
    for a in detail["alerts"]:
        assert all(a[k] for k in ("what", "why", "action", "source"))


def test_unknown_astronaut_404(api):
    assert api.get("/api/crew/Z").status_code == 404
    assert api.get("/api/mirror-gap/Z").status_code == 404


def test_alerts_sorted_worst_first(api):
    alerts = api.get("/api/alerts", params={"day": 25}).json()
    ranks = [a["level"] for a in alerts]
    assert ranks == sorted(ranks, key=lambda lv: lv != "red")
    assert {a["astronaut_id"] for a in alerts} == {"A", "B", "C"}  # A only has the Distance (snapshot) alert


def test_settings_roundtrip(api):
    body = api.post("/api/settings", json={"mission": "moon", "deep_space_mode": True, "current_day": 12}).json()
    assert body["comms_delay"] == "≈1.3 s" and body["current_day"] == 12
    assert api.get("/api/settings").json()["deep_space_mode"] is True
    assert api.get("/api/crew").json()[0]["day"] == 12


def test_mirror_gap_submission(api):
    api.post("/api/settings", json={"mission": "iss", "deep_space_mode": False, "current_day": 25})
    slow = [330, 360, 400, 370, 345, 380, 150, 90]  # one false start (<100), several lapses (>=355)
    body = api.post("/api/mirror-gap/B", json={"self_rating": 8, "reaction_times_ms": slow}).json()
    assert body["false_starts"] == 1 and body["lapses"] == 4 and body["responses"] == 7
    assert body["gap"] > 1.5 and body["level"] in ("amber", "red")
    hist = api.get("/api/mirror-gap/B").json()
    assert hist["items"][-1]["source"] == "submitted" and len(hist["items"]) == 31


def test_mirror_gap_validation(api):
    assert api.post("/api/mirror-gap/A", json={"self_rating": 11, "reaction_times_ms": [300] * 6}).status_code == 422
    assert api.post("/api/mirror-gap/A", json={"self_rating": 5, "reaction_times_ms": [50] * 6}).status_code == 422
    demo = api.post(
        "/api/mirror-gap/A", json={"self_rating": 7, "reaction_times_ms": [280] * 8, "mode": "demo_60s"}
    ).json()
    assert demo["validated"] is False and demo["lapse_band"] is None


def test_out_of_range_day_is_rejected(api):
    for path in ("/api/crew", "/api/dashboard", "/api/alerts", "/api/crew/A"):
        resp = api.get(path, params={"day": 31})
        assert resp.status_code == 422, path
        assert "outside 1-30" in resp.json()["detail"]
    assert api.get("/api/crew", params={"day": 0}).status_code == 422
    assert api.post("/api/isolation/A?day=99", json={"q1": 1, "q2": 1, "q3": 1}).status_code == 422


def test_error_bodies_are_json_detail(api):
    resp = api.get("/api/crew/Z")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Unknown astronaut 'Z'"}


def test_responses_carry_request_id_and_security_headers(api):
    resp = api.get("/health")
    assert len(resp.headers["x-request-id"]) == 12
    assert float(resp.headers["x-process-time-ms"]) >= 0
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert api.get("/health").headers["x-request-id"] != resp.headers["x-request-id"]


def test_large_responses_are_gzipped(api):
    resp = api.get("/api/timeline", headers={"accept-encoding": "gzip"})
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


def test_explicit_day_overrides_saved_day_for_submissions(api):
    api.post("/api/settings", json={"mission": "mars", "deep_space_mode": False, "current_day": 3})
    body = {"q1": 3, "q2": 3, "q3": 2}
    early = api.post("/api/isolation/C", json=body).json()  # saved day 3: little history
    late = api.post("/api/isolation/C?day=25", json=body).json()  # day 25: long high streak
    assert early["level"] == "amber"
    assert late["level"] == "red"


def test_blank_nasa_key_falls_back_to_demo_key():
    from app.core.config import Settings

    assert Settings(nasa_api_key="   ").nasa_api_key == "DEMO_KEY"
    assert Settings(nasa_api_key=" abc ").nasa_api_key == "abc"

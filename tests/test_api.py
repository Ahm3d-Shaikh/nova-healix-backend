def test_health_and_root(api):
    assert api.get("/health").json() == {"status": "healthy"}
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
    demo = api.post("/api/mirror-gap/A", json={"self_rating": 7, "reaction_times_ms": [280] * 8, "mode": "demo_60s"}).json()
    assert demo["validated"] is False and demo["lapse_band"] is None

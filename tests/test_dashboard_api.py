def test_dashboard_single_call(api):
    body = api.get("/api/dashboard", params={"day": 20}).json()
    assert body["day"] == 20 and body["settings"]["comms_delay"]
    assert body["space_weather"]["source"] == "snapshot"
    assert any(e["kind"] == "sep" for e in body["space_weather"]["events_last_24h"])
    assert [c["astronaut"]["id"] for c in body["crew"]] == ["A", "B", "C"]
    rad = next(c for c in body["crew"][0]["cards"] if c["hazard"] == "R")
    assert rad["level"] == "red"
    m = rad["metrics"]
    assert m["career_limit_msv"] == 600 and m["sep_events_24h"] >= 1
    assert 0 < m["percent_of_limit"] < 100 and m["neutron_share_estimate"] == 0.3
    assert body["alerts"] and body["alerts"][0]["level"] == "red"


def test_every_card_has_metrics(api):
    for crew in api.get("/api/dashboard", params={"day": 25}).json()["crew"]:
        assert len(crew["cards"]) == 6 and all(c["metrics"] for c in crew["cards"])
    c = next(x for x in api.get("/api/dashboard", params={"day": 25}).json()["crew"] if x["astronaut"]["id"] == "C")
    grav = next(k for k in c["cards"] if k["hazard"] == "G")["metrics"]
    assert grav["kind"] == "gravity" and grav["resting_hr"]["above_threshold"] is True
    assert grav["exercise_missed_days"] >= 2
    assert grav["drifting"] == ["resting HR"]


def test_timeline_matches_per_day_requests(api):
    tl = api.get("/api/timeline").json()
    assert tl["mission_days"] == 30 and tl["storm_days"] == [20, 21, 22]
    assert all(len(c["days"]) == 30 for c in tl["crew"])
    c = next(x for x in tl["crew"] if x["astronaut_id"] == "C")
    for day in (5, 20, 25):
        direct = {s["astronaut"]["id"]: s for s in api.get("/api/crew", params={"day": day}).json()}["C"]
        assert c["days"][day - 1]["cards"] == direct["cards"] and c["days"][day - 1]["overall"] == direct["overall"]
    assert api.get("/api/timeline", params={"astronaut": "B"}).json()["crew"][0]["astronaut_id"] == "B"
    assert api.get("/api/timeline", params={"astronaut": "Z"}).status_code == 404


def test_isolation_questionnaire_and_submission(api):
    q = api.get("/api/isolation/questionnaire").json()
    assert len(q["questions"]) == 3 and [o["value"] for o in q["options"]] == [1, 2, 3]
    api.post("/api/settings", json={"mission": "mars", "deep_space_mode": False, "current_day": 25})
    low = api.post("/api/isolation/A", json={"q1": 1, "q2": 1, "q3": 2}).json()
    assert low["score"] == 4 and low["level"] == "green"
    high = api.post("/api/isolation/C", json={"q1": 3, "q2": 3, "q3": 2}).json()
    assert high["score"] == 8 and high["level"] == "red" and high["consecutive_days_at_or_above_7"] >= 3
    hist = api.get("/api/isolation/C").json()
    assert hist["items"][-1]["source"] == "submitted" and len(hist["items"]) == 31


def test_isolation_validation(api):
    assert api.post("/api/isolation/A", json={"q1": 4, "q2": 1, "q3": 1}).status_code == 422
    assert api.post("/api/isolation/Z", json={"q1": 1, "q2": 1, "q3": 1}).status_code == 404


def test_timeline_cache_respects_deep_space_mode(api):
    normal = api.get("/api/timeline", params={"astronaut": "A"}).json()
    api.post("/api/settings", json={"mission": "mars", "deep_space_mode": True, "current_day": 5})
    deep = api.get("/api/timeline", params={"astronaut": "A"}).json()
    # Offline fixture serves the snapshot either way, but deep-space mode must never reuse a stale entry.
    assert deep["crew"][0]["days"][4]["cards"]["D"] == "amber"
    assert normal["crew"][0]["astronaut_id"] == deep["crew"][0]["astronaut_id"] == "A"

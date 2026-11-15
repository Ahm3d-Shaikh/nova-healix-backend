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

"""Distance, dashboard and alerts: convenience views on the one core."""

import asyncio

from app.nasa.service import KM_PER_AU
from tests.conftest import rating


def test_distance_is_the_trajectory_in_km_and_light_seconds(api, container):
    d = api.get("/api/distance").json()
    assert d["mission"] == "mars" and d["target"] == "Mars" and d["durationDays"] == 260
    assert d["source"] == "model" and d["asOf"] is None
    assert len(d["days"]) == 261 and d["days"][0]["day"] == 1
    au = container.trajectory.au
    assert d["days"][-1]["distanceKm"] == round(au[260] * KM_PER_AU, 1)
    assert abs(d["days"][-1]["lightTimeS"] - au[260] * 499.005) < 0.01
    assert [p["distanceKm"] for p in d["days"]] == sorted(p["distanceKm"] for p in d["days"])  # moving away


def test_dashboard_is_one_call_with_everything_for_an_overview(api, hour):
    d = api.get("/api/dashboard").json()
    assert d["day"] == 142 and d["durationDays"] == 260 and abs(d["missionHour"] - hour) < 0.01
    assert "not a medical device" in d["disclaimer"]
    assert d["link"]["mode"] == "nominal" and 100 < d["link"]["delaySeconds"] < 600
    assert [c["astronaut"]["id"] for c in d["crew"]] == ["hashir", "ahmad", "hannan", "sabaina"]
    hannan = next(c for c in d["crew"] if c["astronaut"]["id"] == "hannan")
    assert hannan["summary"]["status"] == "alert" and len(hannan["hazards"]) == 5
    assert any(i["id"] == "isolation-stress:hannan" for i in hannan["insights"])
    assert [i["id"] for i in d["crewWideInsights"]] == ["co2:crew"]
    assert d["recentSpaceEvents"] == []  # the storm is on day 97


def test_dashboard_at_a_past_hour_and_autonomous(api, container):
    asyncio.run(container.nasa.refresh())  # offline NASA clients: the bundled real snapshot of the storm
    storm = api.get("/api/dashboard", params={"at": 2312}).json()  # D97, inside the replayed NASA storm
    assert storm["day"] == 97 and storm["recentSpaceEvents"]
    assert all(e["source"] == "NASA DONKI" for e in storm["recentSpaceEvents"])
    auto = api.get("/api/dashboard", params={"autonomous": "true"}).json()
    assert auto["link"]["mode"] == "autonomous"


def test_alerts_are_active_findings_most_urgent_first(api):
    alerts = api.get("/api/alerts").json()
    assert alerts and all(a["severity"] in ("alert", "watch") for a in alerts)
    assert alerts[0]["id"] == "isolation-stress:hannan"  # the one alert
    assert not any(a["id"].startswith("bone-on-track") for a in alerts)  # info is not an alert
    api.post("/api/insights/sleep-debt:ahmad/resolve", json={"crewId": "ahmad", "note": "handled", "severity": "watch"})
    assert not any(a["id"] == "sleep-debt:ahmad" for a in api.get("/api/alerts").json())  # resolved: not active
    dash = api.get("/api/dashboard").json()
    ahmad = next(c for c in dash["crew"] if c["astronaut"]["id"] == "ahmad")
    assert not any(i["id"] == "sleep-debt:ahmad" for i in ahmad["insights"])


def test_an_echo_check_in_shows_up_in_the_dashboard_and_alerts(api, echo_companion):
    echo_companion.next_rating = rating(3, 3, 3, safety=True)
    sid = api.post("/api/isolation/hashir/sessions").json()["session"]["id"]
    for i in range(3):
        api.post(f"/api/isolation/hashir/sessions/{sid}/messages", json={"content": f"m{i}"})
    api.post(f"/api/isolation/hashir/sessions/{sid}/complete")
    assert api.get("/api/alerts").json()[0]["id"] == "loneliness:hashir"
    dash = api.get("/api/dashboard").json()
    hashir = next(c for c in dash["crew"] if c["astronaut"]["id"] == "hashir")
    assert hashir["summary"]["status"] == "alert" and any(i["id"] == "loneliness:hashir" for i in hashir["insights"])

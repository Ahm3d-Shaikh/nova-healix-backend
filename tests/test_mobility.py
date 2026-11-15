"""Mobility & Balance Check: additive endpoints that feed the Gravity hazard and the findings."""

import asyncio

from fastapi.testclient import TestClient

from app.container import build_container
from app.main import create_app
from tests.conftest import NOW_MS

GOOD = {"balanceHoldS": 30, "swayPctHeight": 1.0, "sitToStandS": 9.0, "kneeFlexionDeg": 120, "poseConfidence": 0.9}


def post(api, body, crew="hashir"):
    return api.post(f"/api/mobility/{crew}", json=body)


def gravity(api, crew="hashir"):
    return next(
        h for h in api.get("/api/assessment/hazards").json() if h["crewId"] == crew and h["hazard"] == "gravity"
    )


def mobility_insight(api, crew="hashir"):
    return next((i for i in api.get("/api/insights").json() if i["id"] == f"mobility:{crew}"), None)


def test_method_lists_three_short_tests_and_the_limit(api):
    m = api.get("/api/mobility/method").json()
    assert [t["test"] for t in m["tests"]] == ["balance", "sit_to_stand", "squat_rom"]
    assert m["totalDurationS"] <= 120 and m["minPoseConfidence"] == 0.6 and "bone" in m["limits"]
    assert {"balanceHoldS", "swayPctHeight"} == set(m["tests"][0]["send"])


def test_without_a_check_nothing_changes(api):
    g = gravity(api)
    assert all(d["label"] != "Mobility & balance check" for d in g["drivers"])
    assert mobility_insight(api) is None
    assert api.get("/api/mobility/hashir").json() == {"crewId": "hashir", "checks": [], "latest": None}


def test_good_check_is_nominal_and_adds_a_zero_driver(api):
    before = gravity(api)
    r = post(api, GOOD)
    assert r.status_code == 201
    sub = r.json()
    assert sub["counted"] is True and sub["message"] == "Check saved." and sub["result"]["status"] == "nominal"
    assert sub["check"]["crewId"] == "hashir" and sub["check"]["day"] == 142 and sub["check"]["reliable"] is True
    driver = next(d for d in gravity(api)["drivers"] if d["label"] == "Mobility & balance check")
    assert driver["contribution"] == 0 and "metric" not in driver  # nothing for the frontend to special-case
    assert driver["value"] == "120° squat · 9.0 s sit-to-stand · 30 s balance"
    assert gravity(api)["score"] <= before["score"]  # a healthy check never raises the hazard
    assert mobility_insight(api) is None


def test_slow_sit_to_stand_raises_the_gravity_hazard_and_a_finding(api):
    before = gravity(api, "ahmad")
    r = post(api, {**GOOD, "sitToStandS": 16}, "ahmad").json()
    assert r["result"]["status"] == "alert"
    after = gravity(api, "ahmad")
    d = next(x for x in after["drivers"] if x["label"] == "Mobility & balance check")
    assert d["contribution"] == 85 and "concern" in d
    assert after["score"] > before["score"]
    i = mobility_insight(api, "ahmad")
    assert i["severity"] == "alert" and i["hazards"] == ["gravity"] and i["primaryMetric"] == "legStrength"
    assert "5x sit-to-stand" in i["title"] and "bone" in i["whyItMatters"]
    assert any(e["label"] == "5x sit-to-stand" and e["value"] == "16.0 s for 5 stands" for e in i["evidence"])
    assert i["recommended"][-1]["label"] == "Flag for flight surgeon review"
    summary = {s["crewId"]: s for s in api.get("/api/assessment/crew-summaries").json()}
    assert summary["ahmad"]["status"] == "alert"


def test_watch_levels_per_test(api):
    r = post(api, {**GOOD, "kneeFlexionDeg": 90, "balanceHoldS": 8}).json()["result"]
    assert r["status"] == "watch"
    assert {t["test"]: t["status"] for t in r["tests"]} == {
        "balance": "watch",
        "sit_to_stand": "nominal",
        "squat_rom": "watch",
    }
    assert mobility_insight(api)["severity"] == "watch"


def test_decline_versus_the_first_check_is_flagged_inside_absolute_limits(api):
    post(api, GOOD)
    r = post(api, {**GOOD, "sitToStandS": 11.5}).json()["result"]  # +28 % slower, still under 12 s
    sts = next(t for t in r["tests"] if t["test"] == "sit_to_stand")
    assert sts["status"] == "watch" and sts["changePct"]["sitToStandS"] > 25 and r["checksUsed"] == 2
    assert sts["baseline"] == {"sitToStandS": 9.0}
    first = next(t for t in post(api, GOOD, "sabaina").json()["result"]["tests"] if t["test"] == "balance")
    assert first["baseline"] is None and first["changePct"] is None  # `| null` fields are always sent


def test_low_pose_confidence_is_stored_but_not_used(api):
    r = post(api, {**GOOD, "sitToStandS": 40, "poseConfidence": 0.3}).json()
    assert r["counted"] is False and r["result"] is None and "Retake" in r["message"]
    h = api.get("/api/mobility/hashir").json()
    assert len(h["checks"]) == 1 and h["checks"][0]["reliable"] is False and h["latest"] is None
    assert mobility_insight(api) is None
    assert all(d["label"] != "Mobility & balance check" for d in gravity(api)["drivers"])


def test_validation_and_unknown_astronaut(api):
    assert post(api, {**GOOD, "balanceHoldS": 45}).status_code == 422
    assert post(api, {**GOOD, "sitToStandS": 0}).status_code == 422
    assert post(api, {**GOOD, "kneeFlexionDeg": 171.7}).status_code == 422  # impossible: a tracking error
    assert post(api, {**GOOD, "kneeFlexionDeg": 150}).status_code == 201
    assert post(api, {k: v for k, v in GOOD.items() if k != "kneeFlexionDeg"}).status_code == 422
    assert post(api, GOOD, "zed").status_code == 404 and api.get("/api/mobility/zed").status_code == 404


def test_checks_are_per_astronaut(api):
    post(api, {**GOOD, "sitToStandS": 16}, "hannan")
    assert mobility_insight(api, "hashir") is None and mobility_insight(api, "hannan")["severity"] == "alert"


def test_a_check_applies_from_when_it_was_made(api, hour):
    post(api, {**GOOD, "sitToStandS": 16}, "ahmad")
    earlier = api.get("/api/insights", params={"at": hour - 1}).json()
    assert not any(i["id"] == "mobility:ahmad" for i in earlier)
    assert any(i["id"] == "mobility:ahmad" for i in api.get("/api/insights", params={"at": hour}).json())


def test_resolving_the_finding_works_like_any_other(api):
    post(api, {**GOOD, "kneeFlexionDeg": 90})
    r = api.post(
        "/api/insights/mobility:hashir/resolve",
        json={"crewId": "hashir", "note": "Repeat was fine", "severity": "watch"},
    )
    assert r.status_code == 200 and mobility_insight(api)["resolution"]["note"] == "Repeat was fine"


def test_checks_survive_a_restart(settings, db):
    c1 = asyncio.run(build_container(settings, db, now_ms=NOW_MS))
    with TestClient(create_app(settings, c1)) as api:
        post(api, {**GOOD, "sitToStandS": 16}, "ahmad")
        before = api.get("/api/insights").json()
    assert set(db.table("mobility_sessions")._rows[0]) == {
        "id", "crew_id", "day", "at", "balance_hold_s", "sway_pct_height", "sit_to_stand_s", "knee_flexion_deg", "pose_confidence", "reliable",
    }  # fmt: skip
    c2 = asyncio.run(build_container(settings, db, now_ms=NOW_MS))
    with TestClient(create_app(settings, c2)) as api:
        assert api.get("/api/insights").json() == before
        assert api.get("/api/mobility/ahmad").json()["latest"]["status"] == "alert"


def test_everything_is_camel_case_and_the_page_is_served(api):
    body = post(api, GOOD).json()
    assert all("_" not in k for k in body) and all("_" not in k for k in body["check"]["measurements"])
    page = api.get("/demo/mobility/")
    assert page.status_code == 200 and "Mobility" in page.text and "tasks-vision" in page.text
    assert "hashir" in page.text  # v2 astronaut ids in the picker


def test_a_check_is_visible_to_quarter_aligned_requests_made_just_before_it(api, hour):
    """The frontend asks at quarter-hour-aligned times and results are cached per quarter hour."""
    api.get("/api/assessment/hazards", params={"at": hour - 0.1})  # warms the cache for this quarter
    post(api, {**GOOD, "sitToStandS": 16}, "ahmad")
    for at in (hour - 0.1, hour):
        g = next(
            h
            for h in api.get("/api/assessment/hazards", params={"at": at}).json()
            if h["crewId"] == "ahmad" and h["hazard"] == "gravity"
        )
        assert any(d["label"] == "Mobility & balance check" for d in g["drivers"])
        assert any(i["id"] == "mobility:ahmad" for i in api.get("/api/insights", params={"at": at}).json())
    assert not any(i["id"] == "mobility:ahmad" for i in api.get("/api/insights", params={"at": hour - 0.5}).json())

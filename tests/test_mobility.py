from app.models.enums import Hazard, Level

GOOD = {
    "balance_hold_s": 30,
    "sway_pct_height": 1.0,
    "sit_to_stand_5x_s": 9.0,
    "knee_flexion_deg": 120,
    "pose_confidence": 0.9,
}


def gravity_card(api, aid="A", day=10):
    crew = api.get(f"/api/crew/{aid}", params={"day": day}).json()
    return next(c for c in crew["cards"] if c["hazard"] == Hazard.GRAVITY.value)


def post(api, body, aid="A", day=10):
    return api.post(f"/api/mobility/{aid}", params={"day": day}, json=body)


def test_method_lists_three_short_tests_and_the_limit(api):
    m = api.get("/api/mobility/method").json()
    assert [t["test"] for t in m["tests"]] == ["balance", "sit_to_stand", "squat_rom"]
    assert m["total_duration_s"] <= 120
    assert "bone" in m["limits"]


def test_no_check_means_no_mobility_alert_or_metrics(api):
    card = gravity_card(api)
    assert card["metrics"]["mobility"] is None
    assert all(a["rule"] != "G.mobility" for a in card["alerts"])


def test_good_check_is_green_and_appears_on_the_gravity_card(api):
    r = post(api, GOOD)
    assert r.status_code == 201 and r.json()["counted"] is True
    card = gravity_card(api)
    assert card["level"] == "green"
    mob = card["metrics"]["mobility"]
    assert mob["level"] == "green" and mob["checks_used"] == 1 and mob["last_check_day"] == 10
    assert {t["test"] for t in mob["tests"]} == {"balance", "sit_to_stand", "squat_rom"}


def test_check_does_not_show_on_earlier_days(api):
    post(api, GOOD, day=10)
    assert gravity_card(api, day=9)["metrics"]["mobility"] is None


def test_slow_sit_to_stand_is_red_and_drives_the_card(api):
    post(api, {**GOOD, "sit_to_stand_5x_s": 16})
    card = gravity_card(api)
    assert card["level"] == "red"
    alert = next(a for a in card["alerts"] if a["rule"] == "G.mobility")
    assert "5x sit-to-stand" in alert["what"] and "bone" in alert["why"]


def test_shallow_squat_and_short_hold_are_amber(api):
    post(api, {**GOOD, "knee_flexion_deg": 90, "balance_hold_s": 8})
    r = api.get("/api/mobility/A").json()["latest"]
    assert r["level"] == "amber"
    levels = {t["test"]: t["level"] for t in r["tests"]}
    assert levels == {"balance": "amber", "sit_to_stand": "green", "squat_rom": "amber"}


def test_decline_versus_first_check_is_flagged_even_within_absolute_limits(api):
    post(api, GOOD, day=5)
    post(api, {**GOOD, "sit_to_stand_5x_s": 11.5}, day=10)  # +28 % slower, still < 12 s
    r = api.get("/api/mobility/A").json()["latest"]
    sts = next(t for t in r["tests"] if t["test"] == "sit_to_stand")
    assert sts["level"] == "amber" and sts["change_pct"]["sit_to_stand_5x_s"] > 25
    assert r["checks_used"] == 2


def test_low_pose_confidence_is_stored_but_not_used(api):
    r = post(api, {**GOOD, "sit_to_stand_5x_s": 40, "pose_confidence": 0.3}).json()
    assert r["counted"] is False and r["result"] is None and "Retake" in r["message"]
    assert len(api.get("/api/mobility/A").json()["checks"]) == 1
    assert gravity_card(api)["metrics"]["mobility"] is None


def test_validation_and_unknown_astronaut(api):
    assert post(api, {**GOOD, "balance_hold_s": 45}).status_code == 422
    assert post(api, {**GOOD, "sit_to_stand_5x_s": 0}).status_code == 422
    assert post(api, {k: v for k, v in GOOD.items() if k != "knee_flexion_deg"}).status_code == 422
    assert post(api, GOOD, aid="Z").status_code == 404
    assert post(api, GOOD, day=99).status_code == 422


def test_checks_are_per_astronaut(api):
    post(api, {**GOOD, "sit_to_stand_5x_s": 16}, aid="B")
    assert gravity_card(api, "A")["metrics"]["mobility"] is None
    assert gravity_card(api, "B")["level"] == "red"


def test_dashboard_includes_mobility(api):
    post(api, GOOD)
    dash = api.get("/api/dashboard", params={"day": 10}).json()
    a = next(c for c in dash["crew"] if c["astronaut"]["id"] == "A")
    grav = next(c for c in a["cards"] if c["hazard"] == "G")
    assert grav["metrics"]["mobility"]["level"] == Level.GREEN.value

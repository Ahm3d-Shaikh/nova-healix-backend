"""Endpoint tests for API v2, including the acceptance checklist from the guide (section 10)."""

from urllib.parse import quote

import pytest

from tests.conftest import FakeReplier

CREW = ["hashir", "ahmad", "hannan", "sabaina"]
HAZARDS = ["radiation", "isolation", "distance", "gravity", "environment"]


def camel_only(obj) -> bool:
    """No snake_case key anywhere in a JSON body."""
    if isinstance(obj, dict):
        return all("_" not in k and camel_only(v) for k, v in obj.items())
    if isinstance(obj, list):
        return all(camel_only(v) for v in obj)
    return True


# -- mission / crew -------------------------------------------------------------------------------
def test_mission_config(api, container):
    m = api.get("/api/mission").json()
    assert m["code"] == "NHX-1" and m["durationDays"] == 260 and m["careerDoseLimitMsv"] == 600
    assert len(m["trajectoryAu"]) >= m["durationDays"] + 1  # guide checklist
    assert m["team"] == {"flightSurgeon": "Haleem", "flightDirector": "Hamza"}
    assert m["currentDay"] == 142 and m["launchEpochMs"] == container.clock.launch_epoch_ms


def test_crew_list_and_get(api):
    assert [a["id"] for a in api.get("/api/crew").json()] == CREW
    assert api.get("/api/crew/ahmad").json()["role"] == "FE"
    r = api.get("/api/crew/zed")
    assert r.status_code == 404 and r.json() == {"detail": "Unknown astronaut 'zed'"}  # guide checklist


def test_events_and_timeline_include_exercise(api):
    ids = {e["id"] for e in api.get("/api/mission/events").json()}
    assert {"spe-97", "eva-3", "cdra-140"} <= ids and not any(i.startswith("ex-") for i in ids)
    tl = api.get("/api/crew/hannan/timeline", params={"from": 3300, "to": 3398}).json()
    starts = [e["start"] for e in tl]
    assert starts == sorted(starts)
    assert any(e["kind"] == "exercise" and e.get("missed") for e in tl)  # Hannan's skipped sessions
    assert api.get("/api/crew/zed/timeline", params={"from": 0, "to": 1}).status_code == 404


# -- telemetry -------------------------------------------------------------------------------------
def test_series_window_bucket_and_clamp(api, hour):
    hourly = api.get("/api/crew/ahmad/metrics/hr", params={"from": 3380, "to": 3390}).json()
    assert [s["t"] for s in hourly] == [float(t) for t in range(3380, 3391)]
    bucketed = api.get("/api/crew/ahmad/metrics/hr", params={"from": 0, "to": 100, "bucket": 6}).json()
    assert 15 <= len(bucketed) <= 18
    future = api.get("/api/crew/ahmad/metrics/hr", params={"from": hour - 2, "to": hour + 500}).json()
    assert future and max(s["t"] for s in future) <= hour  # never past now
    assert api.get("/api/crew/ahmad/metrics/nope", params={"from": 0, "to": 1}).status_code == 404
    assert api.get("/api/crew/ahmad/metrics/hr", params={"from": "x", "to": 1}).status_code == 422


def test_baseline_matches_the_guide_example(api):
    b = api.get("/api/crew/ahmad/metrics/hr/baseline").json()
    assert round(b["mean"], 2) == 63.33 and round(b["low"], 2) == 51.34 and b["high"] == 71.9
    assert b["source"] == "In-flight D8–D40, resting"
    assert api.get("/api/crew/ahmad/metrics/radDose/baseline").json() is None  # no band for cumulative dose


def test_live_vitals(api, hour):
    v = api.get("/api/crew/ahmad/vitals/live").json()
    assert v["crewId"] == "ahmad" and abs(v["t"] - hour) < 0.01
    assert set(v["values"]) == {"hr", "hrv", "spo2", "coreTemp", "bpSys", "bpDia", "resp"}
    assert v["values"]["spo2"] <= 100


# -- assessment ----------------------------------------------------------------------------------------
def test_hazards_are_five_per_astronaut_in_canonical_order(api):
    rows = api.get("/api/assessment/hazards").json()
    assert len(rows) == 20  # guide checklist
    for i, crew in enumerate(CREW):
        assert [(r["crewId"], r["hazard"]) for r in rows[i * 5 : i * 5 + 5]] == [(crew, h) for h in HAZARDS]
    for r in rows:
        assert 0 <= r["score"] <= 100 and r["status"] in ("nominal", "watch", "alert")
        assert r["status"] == ("alert" if r["score"] >= 70 else "watch" if r["score"] >= 40 else "nominal")
        contributions = [d["contribution"] for d in r["drivers"]]
        assert contributions == sorted(contributions, reverse=True)
    assert camel_only(rows)


def test_hazard_history_and_autonomous(api):
    h = api.get("/api/assessment/hazards/isolation/history", params={"crew": "hannan", "fromDay": 130}).json()
    assert [s["v"] for s in h][-1] >= 80 and len(h) == 13  # D130..D142
    assert api.get("/api/assessment/hazards/nope/history", params={"crew": "hannan"}).status_code == 404
    assert api.get("/api/assessment/hazards/isolation/history", params={"crew": "zed"}).status_code == 404
    normal = {(r["crewId"], r["hazard"]): r["score"] for r in api.get("/api/assessment/hazards").json()}
    auto = {
        (r["crewId"], r["hazard"]): r["score"]
        for r in api.get("/api/assessment/hazards", params={"autonomous": "true"}).json()
    }
    assert all(auto[k] > normal[k] for k in normal if k[1] == "distance")  # no link raises the distance score


def test_at_is_clamped_to_now(api, hour):
    future = api.get("/api/assessment/hazards", params={"at": hour + 1000}).json()
    now = api.get("/api/assessment/hazards").json()
    assert future == now


def test_crew_summaries(api):
    s = {x["crewId"]: x for x in api.get("/api/assessment/crew-summaries").json()}
    assert s["hashir"]["status"] == "nominal" and s["hannan"]["status"] == "alert"
    assert s["ahmad"]["nextEvent"] == {"label": "EVA-3", "day": 145}
    assert s["hashir"]["nextEvent"] is None and s["hashir"]["checkInHour"] is not None


def test_insights_story(api):
    ins = api.get("/api/insights").json()
    by_id = {i["id"]: i for i in ins}
    assert {
        "sleep-debt:ahmad",
        "isolation-stress:hannan",
        "fluid-shift:sabaina",
        "rad-outlier:sabaina",
        "co2:crew",
    } <= set(by_id)
    assert by_id["co2:crew"]["crewId"] is None  # `| null` fields are always sent
    assert by_id["isolation-stress:hannan"]["severity"] == "alert"
    assert "resolution" not in by_id["sleep-debt:ahmad"] and "reopened" not in by_id["sleep-debt:ahmad"]
    assert camel_only(ins)


def test_interpretation(api):
    r = api.get("/api/crew/ahmad/metrics/sleepDuration/interpretation").json()
    assert r["metric"] == "sleepDuration" and r["trend"] == "down" and r["status"] == "watch"
    assert "below" in r["summary"] and r["recommended"]
    assert api.get("/api/crew/ahmad/metrics/nope/interpretation").status_code == 404


# -- crew mode -----------------------------------------------------------------------------------------
def test_check_in_replaces_same_day_and_validates(api, hour):
    body = {"mood": 3, "sleepQuality": 2, "energy": 3, "symptoms": ["headache"], "note": "  rough night  "}
    first = api.post("/api/crew/hashir/checkins", json=body)
    assert first.status_code == 201
    ci = first.json()
    assert ci["id"] == "ci-hashir-142" and ci["day"] == 142 and ci["note"] == "rough night"
    api.post("/api/crew/hashir/checkins", json={**body, "mood": 5, "note": None})
    todays = [
        c for c in api.get("/api/crew/hashir/checkins", params={"from": 3360, "to": 3400}).json() if c["day"] == 142
    ]
    assert len(todays) == 1 and todays[0]["mood"] == 5 and "note" not in todays[0]
    bad = api.post("/api/crew/hashir/checkins", json={**body, "mood": 9})
    assert bad.status_code == 422 and "mood" in bad.json()["detail"]  # guide checklist
    assert api.post("/api/crew/zed/checkins", json=body).status_code == 404
    assert api.post("/api/crew/hashir/checkins", json={**body, "symptoms": ["flu"]}).status_code == 422


def test_check_in_feeds_the_mood_series_and_the_flag_insight(api):
    api.post("/api/crew/hashir/checkins", json={"mood": 1, "sleepQuality": 3, "energy": 3, "symptoms": []})
    ids = [i["id"] for i in api.get("/api/insights").json()]
    assert "checkin:hashir:142" in ids
    series = api.get("/api/crew/hashir/metrics/mood", params={"from": 3380, "to": 3400}).json()
    assert series[-1]["v"] == 1


def test_questionnaires_assignments_flow(api):
    q = api.get("/api/questionnaires").json()
    assert set(q) == {"wellbeing", "sleep", "workload", "team"} and q["sleep"]["questions"][0]["id"] == "s1"
    assert "feeds" not in q["sleep"] and q["wellbeing"]["feeds"] == "stress"
    a = api.get("/api/crew/hannan/assignments").json()
    team = next(x for x in a if x["questionnaireId"] == "team")
    assert team["status"] == "in-progress" and team["currentIndex"] == 2 and team["answers"] == {"t1": 2, "t2": 4}
    assert api.get("/api/assignments/nope").status_code == 404

    prog = api.put(
        f"/api/assignments/{team['id']}/progress", json={"answers": {"t1": 2, "t2": 4, "t3": 3}, "currentIndex": 3}
    )
    assert prog.status_code == 200 and prog.json()["currentIndex"] == 3 and prog.json()["status"] == "in-progress"

    answers = {"t1": 2, "t2": 4, "t3": 2, "t4": 3, "t5": 2, "t6": "Tired of the same four faces."}
    done = api.post(f"/api/assignments/{team['id']}/submit", json={"answers": answers})
    assert done.status_code == 200
    d = done.json()
    assert d["status"] == "done" and d["currentIndex"] == 6 and d["score"] == 70 and "completedAt" in d
    assert api.post(f"/api/assignments/{team['id']}/submit", json={"answers": answers}).status_code == 409
    q_insight = next(i for i in api.get("/api/insights").json() if i["id"] == f"q:{team['id']}")
    assert q_insight["severity"] == "watch" and any(e["label"] == "Comment" for e in q_insight["evidence"])


def test_submitted_questionnaire_feeds_a_metric(api, hour):
    wb = next(x for x in api.get("/api/crew/ahmad/assignments").json() if x["questionnaireId"] == "wellbeing")
    answers = {"w1": 5, "w2": 1, "w3": 1, "w4": 1, "w5": 5}  # maximum strain
    assert api.post(f"/api/assignments/{wb['id']}/submit", json={"answers": answers}).json()["score"] == 100
    last = api.get("/api/crew/ahmad/metrics/stress", params={"from": 3300, "to": hour}).json()[-1]
    assert last["v"] == 100
    assert api.post("/api/assignments/nope/submit", json={"answers": {}}).status_code == 404
    bad = next(x for x in api.get("/api/crew/ahmad/assignments").json() if x["questionnaireId"] == "sleep")
    assert api.post(f"/api/assignments/{bad['id']}/submit", json={"answers": {"s1": 9}}).status_code == 422
    assert api.post(f"/api/assignments/{bad['id']}/submit", json={"answers": {"zz": 3}}).status_code == 422


# -- Nova ---------------------------------------------------------------------------------------------------
IDLE = {"pendingSafetyCheck": False, "awaitingCheckIn": False}


def nova(api, crew, text=None, history=None, state=None):
    body = {"history": history or [], "state": state or IDLE}
    if text is not None:
        body["text"] = text
    return api.post(f"/api/crew/{crew}/companion/reply", json=body)


def test_nova_greeting_is_personal(api):
    r = nova(api, "hannan").json()
    assert r["replies"][0]["text"].startswith("Hi Hannan.") and r["state"] == IDLE and "safety" not in r
    assert any("sleep has been shorter" in x["text"] for x in r["replies"])  # her own data


def test_nova_check_in_card_has_no_note(api):
    r = nova(api, "hannan", "can you do my check-in? slept badly, feeling low, bit of a headache").json()
    card = r["replies"][0]["card"]
    assert card["kind"] == "checkin" and card["status"] == "proposed"
    assert card["draft"] == {"mood": 2, "sleepQuality": 2, "energy": 2, "symptoms": ["headache"]}


def test_nova_share_card_extracts_only_what_was_asked(api):
    r = nova(api, "hannan", "can you tell Haleem I would like a private call this week").json()
    card = r["replies"][0]["card"]
    assert card == {"kind": "share", "text": "I would like a private call this week", "status": "proposed"}


def test_nova_safety_exception_end_to_end(api, container, db):
    r = nova(api, "ahmad", "I want to die").json()
    assert r["safety"] == {"category": "self-harm", "signal": "wish-to-die"}
    assert r["replies"][0]["card"] == {"kind": "safety", "category": "self-harm"}
    ins = api.get("/api/insights").json()
    first = ins[0]
    assert first["id"].startswith("safety:") and first["severity"] == "alert" and first["crewId"] == "ahmad"
    assert "wish to die" in first["title"] and first["recommended"][0]["kind"] == "message"
    blob = str(ins).lower()
    assert "i want to die" not in blob  # the astronaut's words never reach Mission Control (guide checklist)
    assert api.get("/api/assessment/crew-summaries").json()[1]["status"] == "alert"
    # the saved flag has a category and a signal, no text column at all
    flags = db.table("safety_flags")._rows
    assert len(flags) == 1 and set(flags[0]) == {"id", "crew_id", "at", "category", "signal"}


def test_nova_hopelessness_asks_before_alerting(api):
    r = nova(api, "ahmad", "honestly what's the point").json()
    assert "safety" not in r and r["state"]["pendingSafetyCheck"] is True
    assert not any(i["id"].startswith("safety:") for i in api.get("/api/insights").json())
    yes = nova(api, "ahmad", "yes", state=r["state"]).json()
    assert yes["safety"]["signal"] == "confirmed-when-asked"
    no = nova(api, "hashir", "no, not really", state={"pendingSafetyCheck": True, "awaitingCheckIn": False}).json()
    assert "safety" not in no and no["state"] == IDLE


def test_nova_medical_flag_points_to_the_cmo_or_commander(api):
    r = nova(api, "ahmad", "I have chest pain").json()
    assert r["safety"] == {"category": "medical", "signal": "chest-pain"}
    assert "Sabaina" in r["replies"][0]["text"]
    sab = nova(api, "sabaina", "I have chest pain").json()
    assert "Hashir (commander)" in sab["replies"][0]["text"]  # the CMO is the one who is unwell


def test_nova_never_stores_or_returns_chat(api, db):
    nova(api, "ahmad", "my secret thought is X-RAY-77", history=[{"role": "nova", "text": "Hi"}])
    nova(api, "ahmad", "blah", history=[{"role": "astronaut", "text": "another secret Q-42"}])
    dump = repr({name: t._rows for name, t in db._tables.items()})
    assert "X-RAY-77" not in dump and "Q-42" not in dump
    assert not any("chat" in name or ("message" in name and name != "crew_messages") for name in db._tables)


def test_nova_validation_does_not_echo_the_text(api):
    r = api.post("/api/crew/ahmad/companion/reply", json={"text": "S" * 2001, "history": [], "state": IDLE})
    assert r.status_code == 422 and "SSS" not in r.text
    assert nova(api, "zed").status_code == 404


def test_nova_open_ended_reply_uses_gemini_and_failures_are_503(settings, db):
    import asyncio

    from fastapi.testclient import TestClient

    from app.container import build_container
    from app.main import create_app
    from tests.conftest import NOW_MS

    replier = FakeReplier()
    c = asyncio.run(build_container(settings, db, replier=replier, now_ms=NOW_MS))
    with TestClient(create_app(settings, c)) as api:
        assert api.get("/health").json()["companion"] == "gemini"
        r = nova(
            api, "ahmad", "the quarterly reactor audit went sideways", history=[{"role": "nova", "text": "Hi"}]
        ).json()
        assert r["replies"][0]["text"] == "GEMINI heard 1 turns"
        assert nova(api, "ahmad", "I want to die").json()["safety"]  # safety never goes to the model
        assert replier.calls == ["the quarterly reactor audit went sideways"]
        replier.fail = True
        bad = nova(api, "ahmad", "something else entirely")
        assert bad.status_code == 503 and "Companion unavailable" in bad.json()["detail"]
        assert nova(api, "ahmad", "thanks").status_code == 200  # rule-based answers do not need the model


def test_shared_note_becomes_a_finding(api):
    r = api.post("/api/crew/hannan/shared-notes", json={"text": "Please tell Haleem I would like a private call"})
    assert r.status_code == 201 and r.json()["crewId"] == "hannan"
    note = next(i for i in api.get("/api/insights").json() if i["id"].startswith("note:"))
    assert note["severity"] == "info" and "private call" in note["summary"]
    assert api.post("/api/crew/hannan/shared-notes", json={"text": ""}).status_code == 422


# -- mission control actions --------------------------------------------------------------------------------
def test_record_and_list_actions(api):
    body = {
        "insightId": "sleep-debt:ahmad",
        "crewId": "ahmad",
        "kind": "in-person",
        "label": "In-person check by the CMO",
    }
    r = api.post("/api/actions", json=body)
    assert r.status_code == 201
    e = r.json()
    assert e["by"] == "Haleem" and e["kind"] == "in-person" and "detail" not in e
    assert [x["id"] for x in api.get("/api/actions").json()] == [e["id"]]
    assert api.post("/api/actions", json={**body, "kind": "resolve"}).status_code == 400
    assert api.post("/api/actions", json={**body, "kind": "nope"}).status_code == 422


def test_messages_carry_the_signal_delay_and_log_when_tied_to_a_finding(api, hour):
    r = api.post("/api/crew/ahmad/messages", json={"text": "Ahmad, it's Haleem.", "insightId": "sleep-debt:ahmad"})
    assert r.status_code == 201
    m = r.json()
    delay_h = m["deliverAt"] - m["sentAt"]
    assert m["from"] == "Haleem" and 0.05 < delay_h < 0.15  # about 5.5 minutes at day 142
    assert api.get("/api/crew/ahmad/messages").json()[0]["id"] == m["id"]
    log = api.get("/api/actions").json()
    assert log[-1]["kind"] == "message" and log[-1]["label"] == "Messaged Ahmad" and "arrives 5m" in log[-1]["detail"]
    plain = api.post("/api/crew/ahmad/messages", json={"text": "hello"}).json()
    assert "insightId" not in plain and len(api.get("/api/actions").json()) == 1


def test_resolve_and_reopen_a_finding(api):
    iid = "sleep-debt:ahmad"
    before = next(i for i in api.get("/api/insights").json() if i["id"] == iid)
    assert before["severity"] == "watch"
    r = api.post(
        f"/api/insights/{quote(iid, safe='')}/resolve",
        json={"crewId": "ahmad", "note": "Spoke with Ahmad", "severity": "watch"},
    )
    assert r.status_code == 200 and r.json()["by"] == "Haleem" and r.json()["severity"] == "watch"
    after = next(i for i in api.get("/api/insights").json() if i["id"] == iid)
    assert after["resolution"]["note"] == "Spoke with Ahmad" and "reopened" not in after  # guide checklist
    assert api.get("/api/assessment/crew-summaries").json()[1]["status"] != "alert"
    assert any(e["kind"] == "resolve" and e["detail"] == "Spoke with Ahmad" for e in api.get("/api/actions").json())

    assert api.post(f"/api/insights/{iid}/reopen", json={"crewId": "ahmad"}).json() == {"ok": True}
    again = next(i for i in api.get("/api/insights").json() if i["id"] == iid)
    assert "resolution" not in again  # guide checklist
    assert [e["kind"] for e in api.get("/api/actions").json()] == ["resolve", "reopen"]
    assert (
        api.post(f"/api/insights/{iid}/resolve", json={"crewId": "ahmad", "note": "", "severity": "watch"}).status_code
        == 422
    )


def test_worsened_finding_reopens_itself(api):
    """Resolved at 'info' severity but now 'watch' or worse: it is active again, flagged `reopened`."""
    api.post("/api/insights/sleep-debt:ahmad/resolve", json={"crewId": "ahmad", "note": "ok", "severity": "info"})
    now = next(i for i in api.get("/api/insights").json() if i["id"] == "sleep-debt:ahmad")
    assert now["reopened"] is True and "resolution" not in now


# -- plumbing -----------------------------------------------------------------------------------------------
def test_health_and_root(api, hour):
    h = api.get("/health").json()
    assert h["status"] == "ok" and h["companion"] == "rules" and abs(h["missionHour"] - hour) < 0.01
    assert h["echo"] is True and h["database"] == "memory" and h["version"] == "3.0.0"
    assert "disclaimer" in api.get("/").json()


def test_cors_allows_put_and_the_frontend_origin(api):
    r = api.options(
        "/api/assignments/x/progress",
        headers={
            "Origin": "http://localhost:4200",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code == 200 and "PUT" in r.headers["access-control-allow-methods"]
    assert r.headers["access-control-allow-origin"] == "http://localhost:4200"


def test_one_service_serves_the_guide_and_the_extra_endpoints(api):
    """The guide's endpoints and the extras (ECHO, distance, dashboard, alerts, mobility) share one core."""
    for path in ("/api/dashboard", "/api/distance", "/api/alerts", "/api/isolation/method", "/api/mobility/method"):
        assert api.get(path).status_code == 200
    assert [a["id"] for a in api.get("/api/crew").json()] == ["hashir", "ahmad", "hannan", "sabaina"]
    for gone in ("/api/ridge/crew", "/api/timeline", "/api/ridge/mobility/method"):
        assert api.get(gone).status_code == 404


@pytest.mark.parametrize("path", ["/api/assessment/hazards", "/api/insights", "/api/mission", "/api/crew"])
def test_every_get_is_camel_case(api, path):
    assert camel_only(api.get(path).json())


def test_cors_allows_the_deployed_frontend(api):
    r = api.get("/health", headers={"Origin": "https://nova-helix.vercel.app"})
    assert r.headers["access-control-allow-origin"] == "https://nova-helix.vercel.app"
    assert "access-control-allow-origin" not in api.get("/health", headers={"Origin": "https://evil.example"}).headers

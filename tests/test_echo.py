"""ECHO: the scored isolation check-in chat, on the same crew, clock and database as everything else."""

import asyncio
import json
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient
from google import genai
from google.genai import types as genai_types

from app.container import build_container
from app.core.errors import CompanionUnavailableError
from app.domain import loneliness
from app.domain.personas import PERSONAS
from app.main import create_app
from app.schemas.echo import EchoMessage
from app.services.echo_companion import BLOCKED_REPLY, GeminiEchoCompanion
from app.services.gemini import GeminiClient
from tests.conftest import NOW_MS, rating

HOUR_MS = 3_600_000


def chat(api, crew="ahmad", replies=3):
    start = api.post(f"/api/isolation/{crew}/sessions")
    assert start.status_code == 201
    sid = start.json()["session"]["id"]
    turn = None
    for i in range(replies):
        turn = api.post(f"/api/isolation/{crew}/sessions/{sid}/messages", json={"content": f"reply {i}"})
        assert turn.status_code == 200, turn.text
    return sid, start.json(), turn.json() if turn else None


def isolation(api, crew):
    return next(
        h for h in api.get("/api/assessment/hazards").json() if h["crewId"] == crew and h["hazard"] == "isolation"
    )


def echo_driver(api, crew):
    return next((d for d in isolation(api, crew)["drivers"] if d["label"] == "Loneliness, ECHO check-in"), None)


def finding(api, crew):
    return next((i for i in api.get("/api/insights").json() if i["id"] == f"loneliness:{crew}"), None)


def advance_days(container, days):
    """Move the mission clock forward (ECHO check-ins are per mission day)."""
    container.clock._now_ms = lambda: NOW_MS + days * 24 * HOUR_MS


def test_method_describes_instrument_and_thresholds(api):
    m = api.get("/api/isolation/method").json()
    assert len(m["items"]) == 3 and m["scoreRange"] == [3, 9]
    assert m["minTurns"] == 3 and m["maxTurns"] == 10 and m["minConfidence"] == 0.6
    assert set(m["bands"]) == {"nominal", "watch", "alert", "unreliable"}
    assert api.get("/api/isolation/ahmad").json() == {"crewId": "ahmad", "items": []}


def test_chat_flow_scores_and_feeds_the_isolation_hazard_and_findings(api, echo_companion):
    before = isolation(api, "ahmad")
    sid, start, turn = chat(api, "ahmad")
    assert start["messages"][0]["role"] == "assistant" and "day 142" in start["messages"][0]["content"]
    assert start["session"]["crewId"] == "ahmad" and start["session"]["completedAt"] is None
    assert turn["astronautTurns"] == 3 and turn["canComplete"] and not turn["mustComplete"]
    assert turn["reply"]["content"] == "ECHO heard: reply 2"
    assert echo_companion.reply_calls[-1] == (6, 7)  # opener + 5 messages so far; 10 - 3 replies left

    echo_companion.next_rating = rating(3, 2, 2)  # score 7
    result = api.post(f"/api/isolation/ahmad/sessions/{sid}/complete").json()
    assert result["score"] == 7 and result["status"] == "watch" and result["reliable"] is True
    assert result["missionDay"] == 142 and result["evidence"] == ["e1", "e2", "e3"] and result["model"] == "fake-model"
    assert "elevated" in result["what"] and result["action"] and result["why"] and result["source"]

    d = echo_driver(api, "ahmad")  # the Isolation hazard now has a driver for it
    assert d["value"] == "7/9" and d["contribution"] == 55 and "metric" not in d
    assert isolation(api, "ahmad")["score"] > before["score"]
    f = finding(api, "ahmad")
    assert f["severity"] == "watch" and f["hazards"] == ["isolation"] and "loneliness elevated" in f["title"]
    assert any(e["label"] == "Loneliness score" and e["value"] == "7/9" for e in f["evidence"])

    detail = api.get(f"/api/isolation/ahmad/sessions/{sid}").json()
    assert detail["session"]["status"] == "completed" and len(detail["messages"]) == 7
    assert detail["assessment"]["id"] == result["id"]
    item = api.get("/api/isolation/ahmad").json()["items"][-1]
    assert item == {"day": 142, "score": 7, "status": "watch", "confidence": 0.9, "reliable": True, "sessionId": sid}


def test_nominal_score_adds_a_zero_driver_and_no_finding(api, echo_companion):
    sid, *_ = chat(api, "hashir")
    echo_companion.next_rating = rating(1, 1, 2)
    assert api.post(f"/api/isolation/hashir/sessions/{sid}/complete").json()["status"] == "nominal"
    assert echo_driver(api, "hashir")["contribution"] == 0 and finding(api, "hashir") is None


def test_three_high_days_in_a_row_go_to_alert(api, container, echo_companion):
    echo_companion.next_rating = rating(3, 3, 2)  # 8 each day
    statuses = []
    for day in range(3):
        advance_days(container, day)
        sid, *_ = chat(api, "hannan")
        statuses.append(api.post(f"/api/isolation/hannan/sessions/{sid}/complete").json()["status"])
    assert statuses == ["watch", "watch", "alert"]
    assert finding(api, "hannan")["severity"] == "alert" and echo_driver(api, "hannan")["contribution"] == 85


def test_a_gap_in_the_days_breaks_the_streak():
    series = [(10, 8), (11, 8), (13, 8)]  # day 12 is missing
    assert loneliness.high_streak(series) == 1
    assert loneliness.assess(series).status == "watch"
    assert loneliness.high_streak([(10, 8), (11, 8), (12, 7)]) == 3
    assert loneliness.high_streak([]) == 0 and loneliness.assess([]).status == "nominal"


def test_safety_concern_is_alert_at_once(api, echo_companion):
    echo_companion.next_rating = rating(1, 2, 1, safety=True)
    sid, *_ = chat(api, "sabaina")
    result = api.post(f"/api/isolation/sabaina/sessions/{sid}/complete").json()
    assert result["status"] == "alert" and result["safetyConcern"] is True
    f = finding(api, "sabaina")
    assert f["severity"] == "alert" and f["title"] == "ECHO check-in raised a wellbeing concern"
    assert any(a["id"] == "loneliness:sabaina" for a in api.get("/api/alerts").json())


def test_low_confidence_is_stored_but_does_not_drive_the_hazard(api, echo_companion):
    echo_companion.next_rating = rating(3, 3, 3, confidence=0.3)
    sid, *_ = chat(api, "hannan")
    result = api.post(f"/api/isolation/hannan/sessions/{sid}/complete").json()
    assert result["reliable"] is False and result["status"] == "watch"  # capped
    assert "Low-confidence" in result["what"]
    assert echo_driver(api, "hannan") is None and finding(api, "hannan") is None
    assert len(api.get("/api/isolation/hannan").json()["items"]) == 1  # still stored


def test_unreliable_safety_concern_still_raises_the_alert(api, echo_companion):
    echo_companion.next_rating = rating(1, 1, 1, confidence=0.3, safety=True)
    sid, *_ = chat(api, "hashir")
    result = api.post(f"/api/isolation/hashir/sessions/{sid}/complete").json()
    assert result["reliable"] is False and result["status"] == "alert"
    assert finding(api, "hashir")["severity"] == "alert"  # a person who may be at risk is never hidden


def test_completion_rules(api, echo_companion):
    sid, *_ = chat(api, "ahmad", replies=2)
    resp = api.post(f"/api/isolation/ahmad/sessions/{sid}/complete")
    assert resp.status_code == 409 and "at least 3" in resp.json()["detail"]
    api.post(f"/api/isolation/ahmad/sessions/{sid}/messages", json={"content": "third"})
    first = api.post(f"/api/isolation/ahmad/sessions/{sid}/complete").json()
    echo_companion.next_rating = rating(3, 3, 3)
    assert api.post(f"/api/isolation/ahmad/sessions/{sid}/complete").json()["id"] == first["id"]  # idempotent
    assert api.post(f"/api/isolation/ahmad/sessions/{sid}/messages", json={"content": "more"}).status_code == 409


def test_reply_limit(api):
    sid, _, turn = chat(api, "ahmad", replies=10)
    assert turn["mustComplete"]
    resp = api.post(f"/api/isolation/ahmad/sessions/{sid}/messages", json={"content": "one more"})
    assert resp.status_code == 409 and "limit" in resp.json()["detail"]


def test_session_lookup_errors(api):
    sid, *_ = chat(api, "ahmad", replies=0)
    assert api.get(f"/api/isolation/hannan/sessions/{sid}").status_code == 404  # someone else's session
    assert api.get("/api/isolation/ahmad/sessions/not-a-uuid").status_code == 404
    assert api.get("/api/isolation/ahmad/sessions/00000000-0000-0000-0000-000000000000").status_code == 404
    assert api.post("/api/isolation/zed/sessions").status_code == 404
    assert api.post(f"/api/isolation/ahmad/sessions/{sid}/messages", json={"content": ""}).status_code == 422


def test_failed_reply_saves_nothing_so_the_client_can_resend(api, echo_companion):
    sid, *_ = chat(api, "ahmad", replies=1)
    echo_companion.fail_next = CompanionUnavailableError("Gemini rate limit reached (free tier quota), retry shortly")
    resp = api.post(f"/api/isolation/ahmad/sessions/{sid}/messages", json={"content": "second"})
    assert resp.status_code == 503
    assert len(api.get(f"/api/isolation/ahmad/sessions/{sid}").json()["messages"]) == 3  # unchanged: opener + 1 pair
    retry = api.post(f"/api/isolation/ahmad/sessions/{sid}/messages", json={"content": "second"}).json()
    assert retry["astronautTurns"] == 2 and retry["reply"]["content"] == "ECHO heard: second"
    roles = [m["role"] for m in api.get(f"/api/isolation/ahmad/sessions/{sid}").json()["messages"]]
    assert roles == ["assistant", "astronaut", "assistant", "astronaut", "assistant"]


def test_without_a_gemini_key_echo_returns_503_and_the_rest_works(settings, db):
    c = asyncio.run(build_container(settings, db, now_ms=NOW_MS))  # no ECHO companion
    with TestClient(create_app(settings, c)) as api:
        resp = api.post("/api/isolation/ahmad/sessions")
        assert resp.status_code == 503 and "GEMINI_API_KEY" in resp.json()["detail"]
        assert api.get("/health").json()["echo"] is False
        assert api.get("/api/dashboard").status_code == 200


def test_scores_survive_a_restart(settings, db, echo_companion):
    c1 = asyncio.run(build_container(settings, db, echo_companion=echo_companion, now_ms=NOW_MS))
    echo_companion.next_rating = rating(3, 3, 3)
    with TestClient(create_app(settings, c1)) as api:
        sid, *_ = chat(api, "hannan")
        api.post(f"/api/isolation/hannan/sessions/{sid}/complete")
        before = api.get("/api/insights").json()
    c2 = asyncio.run(build_container(settings, db, echo_companion=echo_companion, now_ms=NOW_MS))
    with TestClient(create_app(settings, c2)) as api:
        assert api.get("/api/insights").json() == before
        assert api.get("/api/isolation/hannan").json()["items"][0]["score"] == 9


# --- GeminiEchoCompanion against a mocked Gemini API -----------------------------------------
ASTRO = PERSONAS["ahmad"].astronaut
MODEL = "gemini-3.8-flash"
LITE = "gemini-3.5-flash-lite"


def transcript() -> list[EchoMessage]:
    now = datetime.now(UTC)
    return [
        EchoMessage(id="1", session_id="s", role="assistant", content="How are things?", created_at=now),
        EchoMessage(id="2", session_id="s", role="astronaut", content="I miss my family.", created_at=now),
    ]


def gemini(handler, chat_model: str | None = None, chat_timeout: float = 20.0) -> GeminiEchoCompanion:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = genai.Client(
        api_key="test",
        http_options=genai_types.HttpOptions(
            httpx_async_client=http, retry_options=genai_types.HttpRetryOptions(attempts=1)
        ),
    )
    return GeminiEchoCompanion(GeminiClient(client, 20.0), MODEL, chat_model, chat_timeout)


def answer(text: str, finish: str = "STOP") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": finish}],
            "modelVersion": MODEL,
        },
    )


def error(code: int, status: str, message: str = "x") -> httpx.Response:
    return httpx.Response(code, json={"error": {"code": code, "message": message, "status": status}})


def test_gemini_reply_request_shape():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return answer("That sounds hard. Who do you talk to most?")

    text = asyncio.run(gemini(handler).reply(ASTRO, 7, transcript(), replies_left=4))
    body = seen["body"]
    assert text.startswith("That sounds hard")
    assert f"models/{MODEL}:generateContent" in seen["url"]
    assert [c["role"] for c in body["contents"]] == ["user", "model", "user"]
    assert "remaining after this one: 4" in body["systemInstruction"]["parts"][0]["text"]
    assert {s["threshold"] for s in body["safetySettings"]} == {"BLOCK_ONLY_HIGH"}


def test_gemini_safety_block_returns_supportive_reply():
    assert asyncio.run(gemini(lambda _: answer("", "SAFETY")).reply(ASTRO, 1, transcript(), 3)) == BLOCKED_REPLY


def test_gemini_empty_reply_is_an_error():
    with pytest.raises(CompanionUnavailableError, match="empty reply"):
        asyncio.run(gemini(lambda _: answer("  ")).reply(ASTRO, 1, transcript(), 3))


def test_gemini_rate_parses_structured_output():
    payload = rating(2, 1, 3, confidence=0.8).model_dump()

    def handler(request: httpx.Request) -> httpx.Response:
        cfg = json.loads(request.content)["generationConfig"]
        assert cfg["responseMimeType"] == "application/json"
        assert set(cfg["responseJsonSchema"]["properties"]) >= {"lack_companionship", "confidence"}
        return answer(json.dumps(payload))

    result = asyncio.run(gemini(handler).rate(ASTRO, 7, transcript()))
    assert (result.lack_companionship.rating, result.left_out.rating, result.isolated.rating) == (2, 1, 3)


@pytest.mark.parametrize(
    "bad",
    ['{"lack_companionship": 7}', json.dumps({**rating().model_dump(), "left_out": {"rating": 5, "evidence": ""}})],
)
def test_gemini_rate_rejects_invalid_rating(bad):
    with pytest.raises(CompanionUnavailableError, match="invalid rating"):
        asyncio.run(gemini(lambda _: answer(bad)).rate(ASTRO, 7, transcript()))


@pytest.mark.parametrize(
    ("response", "needle"),
    [
        (error(429, "RESOURCE_EXHAUSTED"), "free tier"),
        (error(400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key."), "GEMINI_API_KEY"),
        (error(404, "NOT_FOUND"), "GEMINI_MODEL"),
        (error(500, "INTERNAL"), "error 500"),
        (answer("", "SAFETY"), "safety"),
    ],
)
def test_gemini_failures_become_503(response, needle):
    with pytest.raises(CompanionUnavailableError, match=needle):
        asyncio.run(gemini(lambda _: response).rate(ASTRO, 1, transcript()))


def by_model(responses: dict[str, httpx.Response], seen: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        model = next(m for m in responses if f"models/{m}:" in str(request.url))
        seen.append(model)
        return responses[model]

    return handler


def test_chat_uses_the_fast_model_and_rating_uses_the_main_model():
    seen: list[str] = []
    companion = gemini(by_model({LITE: answer("quick reply"), MODEL: answer(rating().model_dump_json())}, seen), LITE)
    assert asyncio.run(companion.reply(ASTRO, 1, transcript(), 3)) == "quick reply"
    asyncio.run(companion.rate(ASTRO, 1, transcript()))
    assert seen == [LITE, MODEL]


@pytest.mark.parametrize("failure", [error(429, "RESOURCE_EXHAUSTED"), error(503, "UNAVAILABLE")])
def test_chat_falls_back_to_main_model_when_fast_model_is_limited(failure):
    seen: list[str] = []
    companion = gemini(by_model({LITE: failure, MODEL: answer("fallback reply")}, seen), LITE)
    assert asyncio.run(companion.reply(ASTRO, 1, transcript(), 3)) == "fallback reply"
    assert seen == [LITE, MODEL]


def test_chat_does_not_retry_errors_that_will_not_fix_themselves():
    seen: list[str] = []
    bad_key = error(400, "INVALID_ARGUMENT", "API key not valid.")
    companion = gemini(by_model({LITE: bad_key, MODEL: answer("unused")}, seen), LITE)
    with pytest.raises(CompanionUnavailableError, match="GEMINI_API_KEY"):
        asyncio.run(companion.reply(ASTRO, 1, transcript(), 3))
    assert seen == [LITE]


def test_chat_times_out_then_falls_back_then_gives_up():
    seen: list[str] = []

    async def slow_then_fast(request: httpx.Request) -> httpx.Response:
        model = LITE if f"models/{LITE}:" in str(request.url) else MODEL
        seen.append(model)
        if model == LITE:
            await asyncio.sleep(1)
        return answer("after timeout")

    reply = asyncio.run(gemini(slow_then_fast, LITE, chat_timeout=0.05).reply(ASTRO, 1, transcript(), 3))
    assert reply == "after timeout" and seen == [LITE, MODEL]

    async def always_slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return answer("never")

    with pytest.raises(CompanionUnavailableError, match="took too long"):
        asyncio.run(gemini(always_slow, LITE, chat_timeout=0.05).reply(ASTRO, 1, transcript(), 3))

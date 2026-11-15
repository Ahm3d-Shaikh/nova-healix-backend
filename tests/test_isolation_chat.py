import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from google import genai
from google.genai import types as genai_types

from app.models.crew import Astronaut
from app.models.isolation import ChatMessage, ChatRole
from app.ridge_container import build_ridge_container as build_container
from app.services.echo_companion import BLOCKED_REPLY, GeminiCompanion
from tests.conftest import combined_app, failing, make_client, make_horizons, rating, set_settings


def chat(api, aid="A", day=None, replies=3):
    params = {"day": day} if day else {}
    start = api.post(f"/api/isolation/{aid}/sessions", params=params)
    assert start.status_code == 201
    sid = start.json()["session"]["id"]
    turn = None
    for i in range(replies):
        turn = api.post(f"/api/isolation/{aid}/sessions/{sid}/messages", json={"content": f"reply {i}"})
        assert turn.status_code == 200, turn.text
    return sid, start.json(), turn.json() if turn else None


def isolation_card(api, aid, day):
    crew = api.get("/api/dashboard", params={"day": day}).json()["crew"]
    cards = next(c for c in crew if c["astronaut"]["id"] == aid)["cards"]
    return next(c for c in cards if c["hazard"] == "I")


def test_method_describes_instrument_and_thresholds(api):
    m = api.get("/api/isolation/method").json()
    assert len(m["items"]) == 3 and m["score_range"] == [3, 9]
    assert m["min_turns"] == 3 and m["min_confidence"] == 0.6
    assert set(m["bands"]) == {"green", "amber", "red", "unreliable"}


def test_chat_flow_scores_and_drives_the_isolation_card(api, companion):
    sid, start, turn = chat(api, "A", day=12)
    assert start["messages"][0]["role"] == "assistant" and "day 12" in start["messages"][0]["content"]
    assert turn["astronaut_turns"] == 3 and turn["can_complete"] and not turn["must_complete"]
    assert turn["reply"]["content"] == "ECHO heard: reply 2"
    assert companion.reply_calls[-1] == (6, 7)  # opener + 5 messages so far; 10 - 3 replies left

    companion.next_rating = rating(3, 2, 2)  # score 7
    result = api.post(f"/api/isolation/A/sessions/{sid}/complete").json()
    assert result["score"] == 7 and result["level"] == "amber" and result["reliable"]
    assert result["mission_day"] == 12 and result["evidence"] == ["e1", "e2", "e3"]
    assert result["model"] == "fake-model"

    card = isolation_card(api, "A", 12)
    assert card["level"] == "amber"
    assert card["metrics"]["loneliness_score"] == 7 and card["metrics"]["latest_source"] == "ai_checkin"
    assert card["metrics"]["ai_checkin_days"] == [12]
    assert isolation_card(api, "A", 11)["metrics"]["latest_source"] == "simulated"

    detail = api.get(f"/api/isolation/A/sessions/{sid}").json()
    assert detail["session"]["status"] == "completed" and len(detail["messages"]) == 7
    assert detail["assessment"]["id"] == result["id"]
    hist = api.get("/api/isolation/A").json()["items"]
    assert hist[-1] == {**hist[-1], "day": 12, "source": "ai_checkin", "score": 7, "session_id": sid}


def test_three_high_days_go_red(api, companion):
    companion.next_rating = rating(3, 3, 2)
    levels = []
    for day in (13, 14, 15):
        sid, *_ = chat(api, "A", day=day)
        levels.append(api.post(f"/api/isolation/A/sessions/{sid}/complete").json()["level"])
    assert levels == ["amber", "amber", "red"]
    assert isolation_card(api, "A", 15)["level"] == "red"


def test_safety_concern_is_red_at_once(api, companion):
    companion.next_rating = rating(1, 2, 1, safety=True)
    sid, *_ = chat(api, "B", day=8)
    result = api.post(f"/api/isolation/B/sessions/{sid}/complete").json()
    assert result["level"] == "red" and result["safety_concern"]
    alerts = api.get("/api/alerts", params={"day": 8}).json()
    assert any(a["rule"] == "I.loneliness" and a["astronaut_id"] == "B" and a["level"] == "red" for a in alerts)


def test_low_confidence_is_stored_but_does_not_drive_the_card(api, companion):
    set_settings(api, "mars", False, 25)
    companion.next_rating = rating(3, 3, 3, confidence=0.3)
    sid, *_ = chat(api, "C")  # C already has a high streak by day 25 -> would be red
    result = api.post(f"/api/isolation/C/sessions/{sid}/complete").json()
    assert not result["reliable"] and result["level"] == "amber"  # capped
    assert "Low-confidence" in result["alert"]["what"]
    assert isolation_card(api, "C", 25)["metrics"]["latest_source"] == "simulated"


def test_completion_rules(api, companion):
    sid, *_ = chat(api, "A", replies=2)
    resp = api.post(f"/api/isolation/A/sessions/{sid}/complete")
    assert resp.status_code == 409 and "at least 3" in resp.json()["detail"]
    api.post(f"/api/isolation/A/sessions/{sid}/messages", json={"content": "third"})
    first = api.post(f"/api/isolation/A/sessions/{sid}/complete").json()
    companion.next_rating = rating(3, 3, 3)
    assert api.post(f"/api/isolation/A/sessions/{sid}/complete").json()["id"] == first["id"]  # idempotent
    closed = api.post(f"/api/isolation/A/sessions/{sid}/messages", json={"content": "more"})
    assert closed.status_code == 409


def test_reply_limit(api):
    sid, _, turn = chat(api, "A", replies=10)
    assert turn["must_complete"]
    resp = api.post(f"/api/isolation/A/sessions/{sid}/messages", json={"content": "one more"})
    assert resp.status_code == 409 and "limit" in resp.json()["detail"]


def test_session_lookup_errors(api):
    sid, *_ = chat(api, "A", replies=0)
    assert api.get(f"/api/isolation/B/sessions/{sid}").status_code == 404  # someone else's session
    assert api.get("/api/isolation/A/sessions/not-a-uuid").status_code == 404
    assert api.get("/api/isolation/A/sessions/00000000-0000-0000-0000-000000000000").status_code == 404
    assert api.post("/api/isolation/Z/sessions").status_code == 404
    assert api.post(f"/api/isolation/A/sessions/{sid}/messages", json={"content": ""}).status_code == 422


def test_without_api_key_checkins_return_503(settings, db):
    container = asyncio.run(build_container(settings, make_client(failing), make_horizons(failing), db, None))
    with TestClient(combined_app(settings, container, db)) as api:
        resp = api.post("/api/isolation/A/sessions")
        assert resp.status_code == 503 and "GEMINI_API_KEY" in resp.json()["detail"]
        assert api.get("/health").json()["ai_checkin"] is False
        assert api.get("/api/dashboard").status_code == 200  # the rest of the app still works


# --- GeminiCompanion against a mocked Gemini API ---------------------------------------------
ASTRO = Astronaut(id="A", name="Astronaut A", role="Commander", story="")
MODEL = "gemini-3.8-flash"


def transcript() -> list[ChatMessage]:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    return [
        ChatMessage(id="1", session_id="s", role=ChatRole.ASSISTANT, content="How are things?", created_at=now),
        ChatMessage(id="2", session_id="s", role=ChatRole.ASTRONAUT, content="I miss my family.", created_at=now),
    ]


def gemini(handler, chat_model: str | None = None, chat_timeout: float = 20.0) -> GeminiCompanion:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = genai.Client(
        api_key="test",
        http_options=genai_types.HttpOptions(
            httpx_async_client=http, retry_options=genai_types.HttpRetryOptions(attempts=1)
        ),
    )
    return GeminiCompanion(client, MODEL, chat_model, chat_timeout)


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
    from app.core.errors import EchoUnavailableError as CompanionUnavailableError

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
    from app.core.errors import EchoUnavailableError as CompanionUnavailableError

    with pytest.raises(CompanionUnavailableError, match=needle):
        asyncio.run(gemini(lambda _: response).rate(ASTRO, 1, transcript()))


# --- Latency: fast chat model, fallback, timeout, no orphaned messages ------------------------
LITE = "gemini-3.5-flash-lite"


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
    from app.core.errors import EchoUnavailableError as CompanionUnavailableError

    seen: list[str] = []
    bad_key = error(400, "INVALID_ARGUMENT", "API key not valid.")
    companion = gemini(by_model({LITE: bad_key, MODEL: answer("unused")}, seen), LITE)
    with pytest.raises(CompanionUnavailableError, match="GEMINI_API_KEY"):
        asyncio.run(companion.reply(ASTRO, 1, transcript(), 3))
    assert seen == [LITE]


def test_chat_times_out_then_falls_back_then_gives_up():
    from app.core.errors import EchoUnavailableError as CompanionUnavailableError

    seen: list[str] = []

    async def slow_then_fast(request: httpx.Request) -> httpx.Response:
        model = LITE if f"models/{LITE}:" in str(request.url) else MODEL
        seen.append(model)
        if model == LITE:
            await asyncio.sleep(1)
        return answer("after timeout")

    assert asyncio.run(gemini(slow_then_fast, LITE, chat_timeout=0.05).reply(ASTRO, 1, transcript(), 3)) == (
        "after timeout"
    )
    assert seen == [LITE, MODEL]

    async def always_slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return answer("never")

    with pytest.raises(CompanionUnavailableError, match="took too long"):
        asyncio.run(gemini(always_slow, LITE, chat_timeout=0.05).reply(ASTRO, 1, transcript(), 3))


def test_failed_reply_saves_nothing_so_the_client_can_resend(api, companion):
    from app.core.errors import EchoUnavailableError as CompanionUnavailableError

    sid, *_ = chat(api, "A", day=3, replies=1)
    companion.fail_next = CompanionUnavailableError("Gemini rate limit reached (free tier quota), retry shortly")
    resp = api.post(f"/api/isolation/A/sessions/{sid}/messages", json={"content": "second"})
    assert resp.status_code == 503
    assert len(api.get(f"/api/isolation/A/sessions/{sid}").json()["messages"]) == 3  # unchanged: opener + 1 pair

    retry = api.post(f"/api/isolation/A/sessions/{sid}/messages", json={"content": "second"}).json()
    assert retry["astronaut_turns"] == 2 and retry["reply"]["content"] == "ECHO heard: second"
    roles = [m["role"] for m in api.get(f"/api/isolation/A/sessions/{sid}").json()["messages"]]
    assert roles == ["assistant", "astronaut", "assistant", "astronaut", "assistant"]

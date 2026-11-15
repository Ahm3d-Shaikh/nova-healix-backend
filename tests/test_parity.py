"""The Python engine must reproduce the frontend's own engine (golden files exported with scripts/dump-golden.ts).

If these fail after a change, the backend no longer agrees with the frontend's built-in demo data.
"""

import json
from pathlib import Path

import pytest

from app.domain import nova
from app.domain.engine.context import EngineContext
from app.domain.engine.hazards import assess_hazards, hazard_history
from app.domain.engine.insights import detect_insights
from app.domain.engine.interpret import interpret_metric
from app.domain.generator import generate_crew
from app.domain.link import LinkState
from app.domain.mission_plan import at, distance_au_on_day
from app.domain.prng import Rng, hash_string
from app.domain.store import MissionData
from app.schemas.nova import CompanionState

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = json.loads((FIXTURES / "nova_golden.json").read_text())
CHAT = json.loads((FIXTURES / "nova_chat_golden.json").read_text())


@pytest.fixture(scope="module")
def db() -> MissionData:
    return MissionData()


def ctx_for(db: MissionData, hod: int) -> EngineContext:
    # The golden run used a fixed day-142 signal delay.
    au = distance_au_on_day(142)
    return EngineContext(db, at(142, hod), LinkState("nominal", au * 499.005, au), 600)


def test_prng_is_bit_identical():
    assert hash_string("nhx-1:ahmad") == 1066254292
    r = Rng("nhx-1:ahmad")
    assert [round(r.next(), 6) for _ in range(3)] == [0.188219, 0.412004, 0.965802]
    assert round(r.gauss(), 6) == 0.868686


@pytest.mark.parametrize("key", sorted(GOLDEN["samples"]))
def test_generated_series_match(key):
    crew, metric = key.split(":")
    ref = GOLDEN["samples"][key]
    s = generate_crew(crew).series[metric]
    assert len(s) == ref["n"]
    assert [(t, v) for t, v in zip(s.t[:4], s.v[:4], strict=False)] == [(x["t"], x["v"]) for x in ref["first"]]
    assert (s.t[-1], s.v[-1]) == (ref["last"]["t"], ref["last"]["v"])


def test_check_ins_and_exercise_match(db):
    for crew in GOLDEN["checkIns"]:
        c = db.check_ins(crew)
        ref = GOLDEN["checkIns"][crew]
        assert len(c) == ref["n"]
        assert (c[0].mood, c[0].sleep_quality, c[0].energy, c[0].symptoms) == (
            ref["first"]["mood"],
            ref["first"]["sleepQuality"],
            ref["first"]["energy"],
            ref["first"]["symptoms"],
        )
        ex = db.exercise(crew)
        assert (len(ex), sum(e.done for e in ex)) == (GOLDEN["exercise"][crew]["n"], GOLDEN["exercise"][crew]["done"])


@pytest.mark.parametrize("key", sorted(GOLDEN["baselines"]))
def test_baselines_match(db, key):
    crew, metric = key.split(":")
    ref = GOLDEN["baselines"][key]
    b = db.baseline(crew, metric)
    if ref is None:
        assert b is None
    else:
        assert (b.mean, b.low, b.high) == pytest.approx((ref["mean"], ref["low"], ref["high"]), abs=1e-6)
        assert b.source == ref["source"]


@pytest.mark.parametrize("hod", ["14", "3"])
def test_hazard_scores_drivers_and_text_match(db, hod):
    run = GOLDEN["runs"][hod]
    got = assess_hazards(ctx_for(db, int(hod)))
    assert len(got) == len(run["hazards"]) == 20
    for h, ref in zip(got, run["hazards"], strict=True):
        assert (h.crew_id, h.hazard, h.score, h.status) == (ref["crewId"], ref["hazard"], ref["score"], ref["status"])
        assert (h.headline, h.explanation) == (ref["headline"], ref["explanation"])
        assert [[d.label, d.value, d.contribution] for d in h.drivers] == ref["drivers"]


@pytest.mark.parametrize("hod", ["14", "3"])
def test_hazard_history_matches(db, hod):
    got = [[round(s.t, 2), s.v] for s in hazard_history(ctx_for(db, int(hod)), "isolation", "hannan", 120, 142)]
    assert got == GOLDEN["runs"][hod]["history"]


@pytest.mark.parametrize("hod", ["14", "3"])
def test_insights_match(db, hod):
    run = GOLDEN["runs"][hod]
    got = [
        (i.id, i.severity, i.title, i.confidence, round(i.detected_at, 6), i.summary)
        for i in detect_insights(ctx_for(db, int(hod)))
    ]
    ref = [
        (i["id"], i["severity"], i["title"], i["confidence"], round(i["detectedAt"], 6), i["summary"])
        for i in run["insights"]
    ]
    assert got == ref


@pytest.mark.parametrize("hod", ["14", "3"])
def test_interpretations_match(db, hod):
    for ref in GOLDEN["runs"][hod]["interp"]:
        r = interpret_metric(ctx_for(db, int(hod)), "ahmad", ref["metric"])
        assert (r.summary, r.trend, r.status, r.confidence, r.why_it_matters) == (
            ref["summary"],
            ref["trend"],
            ref["status"],
            ref["confidence"],
            ref["why"],
        )


# -- Nova ---------------------------------------------------------------------------------------------------
def nova_ctx(db, state=None, prev=None):
    return nova.NovaContext(db, "hannan", at(142, 14), 332, "Haleem", state or CompanionState(), prev)


def card_json(reply):
    return reply.card.model_dump(by_alias=True) if reply.card else None


@pytest.mark.parametrize("text", [k for k in CHAT if not k.startswith("__")])
def test_nova_replies_match(db, text):
    ref = CHAT[text]
    got = nova.respond(nova_ctx(db), text)
    assert [(r.text, card_json(r)) for r in got.replies] == [(r["text"], r.get("card")) for r in ref["replies"]]
    assert (got.safety.model_dump() if got.safety else None) == ref.get("safety")
    assert got.state.model_dump(by_alias=True) == ref["state"]


def test_nova_special_states_match(db):
    def check(got, ref):
        assert [(r.text, card_json(r)) for r in got.replies] == [(r["text"], r.get("card")) for r in ref["replies"]]
        assert (got.safety.model_dump() if got.safety else None) == ref.get("safety")

    check(nova.greeting(nova_ctx(db)), CHAT["__greeting"])
    asked = CompanionState(pending_safety_check=True)
    check(nova.respond(nova_ctx(db, asked), "yes"), CHAT["__yes_after_ask"])
    check(nova.respond(nova_ctx(db, asked), "no"), CHAT["__no_after_ask"])
    check(
        nova.respond(nova_ctx(db, CompanionState(awaiting_check_in=True)), "slept well, feeling great, lots of energy"),
        CHAT["__awaiting"],
    )
    check(nova.respond(nova_ctx(db, prev="I need some time off"), "please tell the doctor"), CHAT["__share_prev"])

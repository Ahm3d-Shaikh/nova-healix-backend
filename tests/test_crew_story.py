"""The simulated crew must tell the stories promised in the spec."""

import asyncio

from app.models.enums import Hazard, Level


def cards(container, aid, day):
    d = asyncio.run(container.crew.detail(aid, day))
    return {c.hazard: c.level for c in d.cards}


def test_generator_is_deterministic(settings, offline_container):
    from app.services.crew_generator import generate_crew
    a = generate_crew(settings.crew_seed, 30, {20})
    b = generate_crew(settings.crew_seed, 30, {20})
    assert a == b and all(len(v) == 30 for v in a.values())


def test_astronaut_a_stays_green_outside_radiation_and_distance(offline_container):
    for day in range(1, 31):
        c = cards(offline_container, "A", day)
        assert {h: lv for h, lv in c.items() if h not in (Hazard.RADIATION, Hazard.DISTANCE)} == {
            Hazard.ISOLATION: Level.GREEN, Hazard.GRAVITY: Level.GREEN,
            Hazard.ENVIRONMENT: Level.GREEN, Hazard.MIRROR: Level.GREEN}, day


def test_b_mirror_gap_goes_amber_then_red(offline_container):
    levels = [cards(offline_container, "B", d)[Hazard.MIRROR] for d in range(1, 31)]
    assert levels[16] == Level.GREEN and Level.AMBER in levels
    assert levels.index(Level.AMBER) < levels.index(Level.RED) and levels[-1] == Level.RED


def test_c_gravity_and_isolation_escalate(offline_container):
    for hazard in (Hazard.GRAVITY, Hazard.ISOLATION):
        levels = [cards(offline_container, "C", d)[hazard] for d in range(1, 31)]
        assert levels[8] == Level.GREEN
        assert levels.index(Level.AMBER) < levels.index(Level.RED) and levels[24] == Level.RED


def test_storm_gives_everyone_a_radiation_alert(offline_container, settings):
    for aid in "ABC":
        assert cards(offline_container, aid, settings.storm_day)[Hazard.RADIATION] == Level.RED
        assert cards(offline_container, aid, 5)[Hazard.RADIATION] == Level.GREEN

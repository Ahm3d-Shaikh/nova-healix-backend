"""Seeded generator for the simulated crew of three (all values are SIMULATED)."""

import random
from statistics import mean
from typing import Callable

from app.models.crew import Astronaut, DailyRecord

ASTRONAUTS: list[Astronaut] = [
    Astronaut(id="A", name="Astronaut A", role="Commander",
              story="Healthy reference: normal noise around a stable baseline."),
    Astronaut(id="B", name="Astronaut B", role="Flight Engineer",
              story="Sleep-deprived from day 18: slow reaction times while self-rating stays 7-8."),
    Astronaut(id="C", name="Astronaut C", role="Mission Specialist",
              story="From day 10: resting HR drifts up, exercise skipped, loneliness score rises."),
]

BASELINE_DOSE_MSV = 0.5  # NASA radiation brief, ~0.5 mSv/day
STORM_DOSE_MSV = 3.0  # extra dose on an SEP day (illustrative)
STORM_AFTERGLOW_MSV = 1.0  # day after (illustrative)

B_ONSET_DAY = 18
C_ONSET_DAY = 10


def generate_crew(seed: int, days: int, sep_days: set[int]) -> dict[str, list[DailyRecord]]:
    """Generate `days` daily records per astronaut. Deterministic for a given seed."""
    builders: dict[str, Callable[[int, random.Random], dict]] = {
        "A": _healthy_day, "B": _sleep_deprived_day, "C": _drifting_day,
    }
    crew: dict[str, list[DailyRecord]] = {}
    for idx, astro in enumerate(ASTRONAUTS):
        rng = random.Random(seed * 10 + idx)
        records: list[DailyRecord] = []
        co2_daily: list[float] = []
        for day in range(1, days + 1):
            fields = builders[astro.id](day, rng)
            co2_mean = rng.gauss(1.9, 0.06)
            co2_daily.append(co2_mean)
            rt = fields.pop("pvt_mean_rt")
            q1, q2, q3 = _split_loneliness(fields.pop("loneliness_total"), rng)
            records.append(DailyRecord(
                day=day,
                co2_mmhg_1h=round(co2_mean + 0.3 + rng.uniform(0, 0.1), 2),
                co2_mmhg_7d=round(mean(co2_daily[-7:]), 2),
                cabin_temp_c=round(rng.gauss(22.5, 0.5), 1),
                loneliness_q1=q1, loneliness_q2=q2, loneliness_q3=q3,
                pvt_mean_rt=round(rt, 1), pvt_mean_speed=round(1000 / rt, 3),
                pvt_false_starts=rng.randint(0, 2),
                dose_msv=round(_dose(day, sep_days, rng), 2),
                **fields,
            ))
        crew[astro.id] = records
    return crew


def _dose(day: int, sep_days: set[int], rng: random.Random) -> float:
    dose = BASELINE_DOSE_MSV + rng.gauss(0, 0.04)
    if day in sep_days:
        dose += STORM_DOSE_MSV
    elif day - 1 in sep_days:
        dose += STORM_AFTERGLOW_MSV
    return max(dose, 0.0)


def _normal_vitals(rng: random.Random) -> dict:
    return {
        "sleep_hours": round(rng.gauss(7.5, 0.4), 1),
        "resting_hr": round(rng.gauss(62, 1.2), 1),
        "sys_bp": round(rng.gauss(118, 2), 1),
        "dia_bp": round(rng.gauss(76, 1.5), 1),
        "exercise_min": round(rng.uniform(35, 60)),
        "pvt_mean_rt": rng.gauss(285, 4),
        "pvt_lapses": rng.randint(2, 5),
        "self_rating": rng.choice([7, 7, 7, 7, 7, 7, 6, 8]),
        "loneliness_total": rng.choice([3, 3, 4]),
    }


def _healthy_day(day: int, rng: random.Random) -> dict:
    return _normal_vitals(rng)


def _sleep_deprived_day(day: int, rng: random.Random) -> dict:
    f = _normal_vitals(rng)
    f["self_rating"] = rng.choice([7, 7, 7, 8])  # stays 7-8 the whole mission
    if day >= B_ONSET_DAY:
        k = day - B_ONSET_DAY
        f["sleep_hours"] = round(rng.gauss(5.0, 0.2), 1)
        f["pvt_lapses"] = min(22, 15 + k // 2 + rng.randint(0, 1))
        f["pvt_mean_rt"] = 300 + 2.5 * k + rng.gauss(0, 3)
    return f


def _drifting_day(day: int, rng: random.Random) -> dict:
    f = _normal_vitals(rng)
    f["self_rating"] = rng.choice([7, 7, 7, 7, 6])
    if day >= C_ONSET_DAY:
        k = day - C_ONSET_DAY + 1
        f["resting_hr"] = round(rng.gauss(62 + 0.5 * k, 1.2), 1)
        f["exercise_min"] = rng.choice([0, 0, 5])
        f["loneliness_total"] = min(8, 4 + round(k * 0.45)) if k < 10 else rng.choice([7, 8])
    return f


def _split_loneliness(total: int, rng: random.Random) -> tuple[int, int, int]:
    """Spread a 3-9 total across the three 1-3 scored questions."""
    q = [1, 1, 1]
    for _ in range(max(0, min(6, total - 3))):
        q[rng.choice([i for i in range(3) if q[i] < 3])] += 1
    return q[0], q[1], q[2]

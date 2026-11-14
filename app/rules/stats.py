"""Small statistics helpers shared by rules."""

from statistics import mean, stdev
from typing import Sequence


def mean_sd(values: Sequence[float], sd_floor: float) -> tuple[float, float]:
    """Sample mean and SD; the SD never drops below `sd_floor`.

    The floors (illustrative) stop a quiet baseline from turning ordinary
    noise into false alarms.
    """
    sd = stdev(values) if len(values) > 1 else 0.0
    return mean(values), max(sd, sd_floor)


def zscore(value: float, mu: float, sd: float) -> float:
    return (value - mu) / sd


def trailing_streak(flags: Sequence[bool]) -> int:
    """Number of consecutive True values at the end of `flags`."""
    n = 0
    for flag in reversed(flags):
        if not flag:
            break
        n += 1
    return n

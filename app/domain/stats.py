"""Series helpers. A series is a pair of parallel lists (times, values), sorted by time."""

import math
from bisect import bisect_left
from dataclasses import dataclass, field


@dataclass
class Series:
    t: list[float] = field(default_factory=list)
    v: list[float] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.t)

    def add(self, t: float, v: float) -> None:
        self.t.append(t)
        self.v.append(v)

    def insert_sorted(self, t: float, v: float) -> None:
        i = bisect_left(self.t, t)
        self.t.insert(i, t)
        self.v.insert(i, v)

    def lower_bound(self, time: float) -> int:
        return bisect_left(self.t, time)

    def slice(self, start: float, end: float) -> "Series":
        """Samples with start <= t <= end."""
        lo = self.lower_bound(start)
        hi = self.lower_bound(end + 1e-9)
        return Series(self.t[lo:hi], self.v[lo:hi])

    def last_at(self, time: float) -> tuple[float, float] | None:
        i = self.lower_bound(time + 1e-9) - 1
        return (self.t[i], self.v[i]) if i >= 0 else None

    def pairs(self) -> list[tuple[float, float]]:
        return list(zip(self.t, self.v, strict=True))


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else math.nan


def sd(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return math.sqrt(sum((x - m) ** 2 for x in values) / (len(values) - 1))


def percentile(values: list[float], p: float) -> float:
    if not values:
        return math.nan
    s = sorted(values)
    idx = (len(s) - 1) * p
    lo = math.floor(idx)
    hi = math.ceil(idx)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def slope(series: Series) -> float:
    """Least-squares slope (value per hour)."""
    if len(series) < 2:
        return 0.0
    mt, mv = mean(series.t), mean(series.v)
    num = sum((t - mt) * (v - mv) for t, v in zip(series.t, series.v, strict=True))
    den = sum((t - mt) ** 2 for t in series.t)
    return num / den if den else 0.0


def downsample(series: Series, bucket_hours: float) -> Series:
    """Mean per fixed-width bucket; t = the bucket's last sample time."""
    if bucket_hours <= 1 or not len(series):
        return series
    out = Series()
    bucket = math.floor(series.t[0] / bucket_hours)
    total, count, last_t = 0.0, 0, 0.0
    for t, v in zip(series.t, series.v, strict=True):
        b = math.floor(t / bucket_hours)
        if b != bucket and count:
            out.add(last_t, total / count)
            total, count, bucket = 0.0, 0, b
        total += v
        count += 1
        last_t = t
    if count:
        out.add(last_t, total / count)
    return out

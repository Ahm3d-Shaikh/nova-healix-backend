"""Seeded PRNG, bit-for-bit compatible with the frontend's `prng.ts` (mulberry32 + Box-Muller).

Same seed, same sequence, so the simulated crew data matches the frontend's built-in demo data.
"""

import math

_M32 = 0xFFFFFFFF


def _imul(a: int, b: int) -> int:
    """JS Math.imul on unsigned 32-bit patterns."""
    return ((a & _M32) * (b & _M32)) & _M32


def hash_string(s: str) -> int:
    """FNV-1a 32-bit (UTF-16 code units, as JS charCodeAt)."""
    h = 2166136261
    data = s.encode("utf-16-le")
    for i in range(0, len(data), 2):
        h ^= data[i] | (data[i + 1] << 8)
        h = _imul(h, 16777619)
    return h & _M32


def js_round(x: float) -> float:
    """JS Math.round: halves round toward +infinity (Python's round() is banker's)."""
    return math.floor(x + 0.5)


def round_to(v: float, digits: int) -> float:
    f = 10.0**digits
    return js_round(v * f) / f


def clamp(v: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, v))


class Rng:
    def __init__(self, seed: int | str) -> None:
        self._state = (hash_string(seed) if isinstance(seed, str) else seed) & _M32
        self._spare: float | None = None

    def next(self) -> float:
        """Uniform [0, 1)."""
        self._state = (self._state + 0x6D2B79F5) & _M32
        t = self._state
        t = _imul(t ^ (t >> 15), t | 1)
        t ^= (t + _imul(t ^ (t >> 7), t | 61)) & _M32
        return ((t ^ (t >> 14)) & _M32) / 4294967296

    def gauss(self) -> float:
        if self._spare is not None:
            s, self._spare = self._spare, None
            return s
        u = 0.0
        v = 0.0
        while u == 0:
            u = self.next()
        while v == 0:
            v = self.next()
        mag = math.sqrt(-2 * math.log(u))
        self._spare = mag * math.sin(2 * math.pi * v)
        return mag * math.cos(2 * math.pi * v)

    def chance(self, p: float) -> bool:
        return self.next() < p


class ArNoise:
    """First-order autoregressive noise: smooth, realistic physiological drift."""

    def __init__(self, rng: Rng, sd: float, phi: float = 0.7) -> None:
        self._rng = rng
        self._sd = sd
        self._phi = phi
        self._k = math.sqrt(1 - phi * phi)
        self._value = 0.0

    def step(self) -> float:
        self._value = self._phi * self._value + self._k * self._sd * self._rng.gauss()
        return self._value

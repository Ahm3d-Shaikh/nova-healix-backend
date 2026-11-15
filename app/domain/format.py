"""Display formatting, matching the frontend's `util/format.ts` (strings appear in findings)."""

import math
from decimal import ROUND_HALF_UP, Decimal

from app.domain.metrics import METRICS


def _pad(n: float, w: int = 2) -> str:
    return str(math.floor(n)).zfill(w)


def mission_day(hour: float) -> int:
    return math.floor(hour / 24) + 1


def format_mission_time(hour: float) -> str:
    """'D142 14:32'"""
    d = mission_day(hour)
    hod = hour - (d - 1) * 24
    hh = math.floor(hod)
    mm = math.floor((hod - hh) * 60)
    return f"D{d} {_pad(hh)}:{_pad(mm)}"


def format_clock(hour: float) -> str:
    """'14:32' ship time (UTC)."""
    hod = ((hour % 24) + 24) % 24
    hh = math.floor(hod)
    mm = math.floor((hod - hh) * 60)
    return f"{_pad(hh)}:{_pad(mm)}"


def format_delay(seconds: float) -> str:
    """'5m 29s'"""
    return f"{math.floor(seconds / 60)}m {_pad(math.floor(seconds % 60))}s"


def to_fixed(v: float, decimals: int) -> str:
    """JS Number.prototype.toFixed: halves round away from zero (Python's format rounds half-even)."""
    if not math.isfinite(v):
        return "NaN" if math.isnan(v) else ("Infinity" if v > 0 else "-Infinity")
    q = Decimal(1).scaleb(-decimals)
    out = Decimal(abs(v)).quantize(q, rounding=ROUND_HALF_UP)
    text = f"{out:f}"
    return f"-{text}" if v < 0 and float(text) != 0 else text if v >= 0 or float(text) != 0 else text


def format_number(v: float, decimals: int) -> str:
    if not math.isfinite(v):
        return "—"
    return to_fixed(v, decimals)


def format_metric(metric: str, v: float, with_unit: bool = True) -> str:
    d = METRICS[metric]
    n = format_number(v, d.decimals)
    if not with_unit or not d.unit:
        return n
    return f"{n}{d.unit}" if d.unit.startswith("/") or d.unit in ("%", "°C") else f"{n} {d.unit}"


def format_signed(v: float, decimals: int) -> str:
    n = to_fixed(abs(v), decimals)
    if float(n) == 0:
        return f"±{n}"
    return f"{'+' if v > 0 else '−'}{n}"


def format_pct(v: float, decimals: int = 0) -> str:
    return f"{format_signed(v, decimals)}%"

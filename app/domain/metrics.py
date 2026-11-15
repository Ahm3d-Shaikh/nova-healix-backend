"""Metric catalogue (units, cadence, thresholds), exported from the frontend's `metric.ts`."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

Concern = Literal["high", "low", "both"]


@dataclass(frozen=True)
class Threshold:
    value: float
    level: Literal["watch", "alert"]
    direction: Literal["above", "below"]


@dataclass(frozen=True)
class MetricDef:
    key: str
    label: str
    short: str
    unit: str
    decimals: int
    group: str
    cadence: str  # hourly | daily | weekly | monthly | session
    hazards: tuple[str, ...]
    concern: Concern
    thresholds: tuple[Threshold, ...]
    range: tuple[float, float]
    source: str


def _load() -> dict[str, MetricDef]:
    raw = json.loads((DATA_DIR / "metrics.json").read_text())
    return {
        key: MetricDef(
            key=key,
            label=m["label"],
            short=m["short"],
            unit=m["unit"],
            decimals=m["decimals"],
            group=m["group"],
            cadence=m["cadence"],
            hazards=tuple(m["hazards"]),
            concern=m["concern"],
            thresholds=tuple(Threshold(t["value"], t["level"], t["direction"]) for t in m["thresholds"]),
            range=(m["range"][0], m["range"][1]),
            source=m["source"],
        )
        for key, m in raw.items()
    }


METRICS: dict[str, MetricDef] = _load()
VITAL_KEYS: tuple[str, ...] = ("hr", "hrv", "spo2", "coreTemp", "bpSys", "bpDia", "resp")
CHECKIN_METRICS: frozenset[str] = frozenset({"mood", "energy", "sleepQuality"})

# Hazard catalogue (labels and countermeasures), from the frontend's `hazard.ts`.
HAZARD_COUNTERMEASURES: dict[str, list[str]] = {
    "radiation": [
        "Storm shelter (water-wall crew quarters) during solar particle events",
        "Duty-cycle scheduling to limit time in low-shielding modules",
        "Personal dosimeter compliance check",
    ],
    "isolation": [
        "Private psychological conference (delayed-link video)",
        "Protected off-duty time and crew-choice activities",
        "Lighting and sleep-schedule adjustment",
    ],
    "distance": [
        "Onboard medical decision support and CMO protocols",
        "Workload re-planning to protect margin",
        "Pre-queued consults with Earth flight surgeon",
    ],
    "gravity": [
        "Resistive and aerobic exercise prescription",
        "Lower-body negative pressure sessions",
        "Ocular imaging and vision checks",
    ],
    "environment": [
        "CO₂ scrubber maintenance and module ventilation",
        "Noise and light hygiene in crew quarters",
        "Environmental sampling",
    ],
}

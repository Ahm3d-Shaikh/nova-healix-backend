from enum import StrEnum


class Level(StrEnum):
    GREEN = "green"
    AMBER = "amber"
    RED = "red"

    @property
    def rank(self) -> int:
        return _RANK[self]


_RANK = {Level.GREEN: 0, Level.AMBER: 1, Level.RED: 2}


def worst(levels: "list[Level] | tuple[Level, ...]") -> Level:
    """Worst (most severe) level; green when empty."""
    return max(levels, key=lambda lv: lv.rank, default=Level.GREEN)


class Hazard(StrEnum):
    """NASA's five spaceflight hazards (RIDGE) plus our Mirror Gap check."""

    RADIATION = "R"
    ISOLATION = "I"
    DISTANCE = "D"
    GRAVITY = "G"
    ENVIRONMENT = "E"
    MIRROR = "MIRROR"


HAZARD_LABELS: dict[Hazard, str] = {
    Hazard.RADIATION: "Radiation",
    Hazard.ISOLATION: "Isolation & confinement",
    Hazard.DISTANCE: "Distance from Earth",
    Hazard.GRAVITY: "Gravity fields",
    Hazard.ENVIRONMENT: "Hostile / closed environments",
    Hazard.MIRROR: "Mirror Gap",
}

RIDGE_HAZARDS: tuple[Hazard, ...] = (
    Hazard.RADIATION,
    Hazard.ISOLATION,
    Hazard.DISTANCE,
    Hazard.GRAVITY,
    Hazard.ENVIRONMENT,
)


class Mission(StrEnum):
    ISS = "iss"
    MOON = "moon"
    MARS = "mars"


COMMS_DELAY: dict[Mission, str] = {
    Mission.ISS: "0 s",
    Mission.MOON: "≈1.3 s",
    Mission.MARS: "3–22 min",
}


class DataSource(StrEnum):
    LIVE = "live"
    CACHED = "cached"
    SNAPSHOT = "snapshot"


class EventKind(StrEnum):
    SEP = "sep"
    FLARE = "flare"
    CME = "cme"
    GEOSTORM = "geostorm"
    NOTIFICATION = "notification"

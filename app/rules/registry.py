"""Machine-readable list of every threshold with its provenance (NFR-05)."""

from app.models.meta import Provenance as P
from app.models.meta import ThresholdInfo
from app.rules import thresholds as t

_NASA_RAD = "NASA radiation protection technical brief / NASA-STD-3001"
_CO2 = "NASA-STD-3001 V2 6004 / NASA OCHMO CO2 briefs"


def _row(hazard: str, name: str, value: float | str, unit: str, prov: P, source: str) -> ThresholdInfo:
    return ThresholdInfo(hazard=hazard, name=name, value=value, unit=unit, provenance=prov, source=source)


THRESHOLD_REGISTRY: tuple[ThresholdInfo, ...] = (
    _row("R", "Career dose limit", t.CAREER_DOSE_LIMIT_MSV, "mSv", P.NASA, _NASA_RAD),
    _row("R", "Per-solar-particle-event dose limit", t.SPE_DOSE_LIMIT_MSV, "mSv", P.NASA, _NASA_RAD),
    _row("R", "Cumulative dose amber at", t.CAREER_AMBER_FRACTION, "fraction of career limit", P.ILLUSTRATIVE, "ours"),
    _row("R", "Cumulative dose red at", t.CAREER_RED_FRACTION, "fraction of career limit", P.ILLUSTRATIVE, "ours"),
    _row("R", "Estimated neutron share of dose", t.NEUTRON_SHARE, "fraction", P.CSA, "CSA Radi-N2 (estimate)"),
    _row("R", "ISS neutron dose", t.ISS_NEUTRON_USV_PER_DAY, "µSv/day", P.CSA, "CSA Radi-N2 (estimate)"),
    _row(
        "R",
        "SEP event -> red; X-class flare / CME -> amber",
        t.EVENT_LOOKBACK_HOURS,
        "hours lookback",
        P.ILLUSTRATIVE,
        "NASA DONKI events; level mapping is ours",
    ),
    _row(
        "I",
        "Loneliness amber from score",
        t.LONELINESS_AMBER_MIN,
        "points (scale 3-9)",
        P.PUBLISHED_METHOD,
        "Three-Item Loneliness Scale (Hughes et al., 2004)",
    ),
    _row("I", "Loneliness red from score", t.LONELINESS_RED_MIN, "points", P.ILLUSTRATIVE, "ours"),
    _row("I", "Loneliness red after consecutive days", t.LONELINESS_RED_DAYS, "days", P.ILLUSTRATIVE, "ours"),
    _row("D", "Cached/snapshot data or Deep space mode -> amber", "amber", "", P.ILLUSTRATIVE, "ours"),
    _row("G", "Baseline window", t.BASELINE_DAYS, "days", P.ILLUSTRATIVE, "ours"),
    _row("G", "Flag when above baseline mean +", t.SD_MULTIPLIER, "SD", P.ILLUSTRATIVE, "ours"),
    _row("G", "Consecutive days above baseline to flag", t.DRIFT_STREAK_DAYS, "days", P.ILLUSTRATIVE, "ours"),
    _row("G", "Exercise counts as missed below", t.MISSED_EXERCISE_MIN, "min", P.ILLUSTRATIVE, "ours"),
    _row("G", "Missed exercise consecutive days to flag", t.MISSED_EXERCISE_DAYS, "days", P.ILLUSTRATIVE, "ours"),
    _row("E", "CO2 7-day average amber above", t.CO2_7D_LIMIT_MMHG, "mmHg", P.NASA, _CO2),
    _row("E", "CO2 1-hour average red above", t.CO2_1H_LIMIT_MMHG, "mmHg", P.NASA, _CO2),
    _row("E", "Cabin temperature minimum", t.TEMP_MIN_C, "°C", P.NASA, "NASA ECLSS technical brief"),
    _row("E", "Cabin temperature maximum", t.TEMP_MAX_C, "°C", P.NASA, "NASA ECLSS technical brief"),
    _row("MIRROR", "PVT lapse threshold", t.PVT_LAPSE_MS, "ms", P.PUBLISHED_METHOD, "PVT-B (Basner et al., 2011)"),
    _row(
        "MIRROR", "PVT false start below", t.PVT_FALSE_START_MS, "ms", P.PUBLISHED_METHOD, "PVT-B (Basner et al., 2011)"
    ),
    _row(
        "MIRROR",
        "Lapse band: reduced from",
        t.LAPSE_BAND_REDUCED,
        "lapses (3-min test)",
        P.PUBLISHED_METHOD,
        "Basner & Rubinstein 2011",
    ),
    _row(
        "MIRROR",
        "Lapse band: poor from",
        t.LAPSE_BAND_POOR,
        "lapses (3-min test)",
        P.PUBLISHED_METHOD,
        "Basner & Rubinstein 2011",
    ),
    _row("MIRROR", "Baseline sessions", t.GAP_BASELINE_SESSIONS, "sessions", P.ILLUSTRATIVE, "ours"),
    _row("MIRROR", "Gap amber above", t.GAP_AMBER, "z-score difference", P.ILLUSTRATIVE, "ours"),
    _row("MIRROR", "Gap red above", t.GAP_RED, "z-score difference", P.ILLUSTRATIVE, "ours"),
    _row("MIRROR", "Consecutive days for gap alert", t.GAP_CONSECUTIVE_DAYS, "days", P.ILLUSTRATIVE, "ours"),
)

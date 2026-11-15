"""Single source of truth for every threshold used by rules and metrics.

Each value is tagged with its provenance:
  [NASA]  published limit (NASA-STD-3001 / NASA OCHMO technical briefs)
  [CSA]   published figure (CSA Radi-N2)
  [PAPER] published method (PVT-B, Basner et al.; Hughes et al. 2004)
  [OURS]  invented for this prototype - always shown as "illustrative"
"""

from typing import Final

# --- Radiation ---------------------------------------------------------------
CAREER_DOSE_LIMIT_MSV: Final = 600.0  # [NASA] career limit
SPE_DOSE_LIMIT_MSV: Final = 250.0  # [NASA] per solar particle event
CAREER_AMBER_FRACTION: Final = 0.80  # [OURS]
CAREER_RED_FRACTION: Final = 0.95  # [OURS]
NEUTRON_SHARE: Final = 0.30  # [CSA] estimate
ISS_NEUTRON_USV_PER_DAY: Final = 150  # [CSA] Radi-N2
EVENT_LOOKBACK_HOURS: Final = 24  # [OURS] "recent" window for DONKI events
FLARE_ALERT_CLASS: Final = "X"  # [OURS] flare class that raises amber

# --- Isolation (Three-Item Loneliness Scale) -----------------------------------
LONELINESS_MIN: Final = 3  # [PAPER]
LONELINESS_MAX: Final = 9  # [PAPER]
LONELINESS_AMBER_MIN: Final = 6  # [PAPER] 6-9 elevated
LONELINESS_RED_MIN: Final = 7  # [OURS]
LONELINESS_RED_DAYS: Final = 3  # [OURS]

# --- Isolation: AI check-in companion ------------------------------------------
CHECKIN_MIN_TURNS: Final = 3  # [OURS] astronaut replies needed before the chat can be scored
CHECKIN_MAX_TURNS: Final = 10  # [OURS] astronaut replies after which the chat must be scored
CHECKIN_MIN_CONFIDENCE: Final = 0.6  # [OURS] below this a rating is stored but never drives the card

# --- Distance (JPL Horizons) -----------------------------------------------------
SPEED_OF_LIGHT_KM_S: Final = 299_792.458  # physical constant
REALTIME_COMMS_MAX_S: Final = 10.0  # [OURS] one-way delay that still allows a live conversation
DISTANCE_AMBER_LIGHT_TIME_S: Final = 300.0  # [OURS] one-way delay >= 5 min: crew must self-manage events

# --- Gravity (cardiovascular flag) ---------------------------------------------
BASELINE_DAYS: Final = 7  # [OURS]
SD_MULTIPLIER: Final = 2.0  # [OURS]
DRIFT_STREAK_DAYS: Final = 3  # [OURS]
MISSED_EXERCISE_MIN: Final = 10  # [OURS] minutes below which exercise counts as missed
MISSED_EXERCISE_DAYS: Final = 2  # [OURS]
HR_SD_FLOOR: Final = 1.5  # [OURS] bpm - stops a quiet baseline causing false alarms
SYS_BP_SD_FLOOR: Final = 3.0  # [OURS] mmHg
DIA_BP_SD_FLOOR: Final = 2.0  # [OURS] mmHg

# --- Gravity: Mobility & Balance Check (movement only; NOT bone health) -----------------
MOBILITY_MIN_CONFIDENCE: Final = 0.6  # [OURS] mean pose-keypoint confidence below which a check is not used
BALANCE_HOLD_MAX_S: Final = 30.0  # [OURS] single-leg stance is stopped at 30 s
BALANCE_HOLD_AMBER_S: Final = 10.0  # [OURS] hold shorter than this -> amber (illustrative)
BALANCE_HOLD_RED_S: Final = 5.0  # [OURS] hold shorter than this -> red (illustrative)
SIT_STAND_AMBER_S: Final = 12.0  # [OURS] 5 sit-to-stands slower than this -> amber (illustrative)
SIT_STAND_RED_S: Final = 15.0  # [OURS] slower than this -> red (illustrative)
KNEE_FLEXION_AMBER_DEG: Final = 100.0  # [OURS] squat depth shallower than this -> amber (illustrative)
KNEE_FLEXION_RED_DEG: Final = 80.0  # [OURS] shallower than this -> red (illustrative)
MOBILITY_CHANGE_AMBER: Final = 0.25  # [OURS] 25 % worse than the astronaut's first check -> amber
MOBILITY_CHANGE_RED: Final = 0.50  # [OURS] 50 % worse than the first check -> red

# --- Environment ---------------------------------------------------------------
CO2_7D_LIMIT_MMHG: Final = 2.5  # [NASA] keeps headache risk < 1 %
CO2_1H_LIMIT_MMHG: Final = 3.0  # [NASA] NASA-STD-3001 V2 6004
TEMP_MIN_C: Final = 18.0  # [NASA] ECLSS operating range
TEMP_MAX_C: Final = 27.0  # [NASA]

# --- Mirror Gap / PVT-B ---------------------------------------------------------
PVT_LAPSE_MS: Final = 355  # [PAPER] Basner et al. 2011
PVT_FALSE_START_MS: Final = 100  # [PAPER]
LAPSE_BAND_REDUCED: Final = 11  # [PAPER] 3-min PVT: <11 good
LAPSE_BAND_POOR: Final = 20  # [PAPER] >=20 poor
GAP_BASELINE_SESSIONS: Final = 5  # [OURS]
GAP_AMBER: Final = 1.0  # [OURS]
GAP_RED: Final = 1.5  # [OURS]
GAP_CONSECUTIVE_DAYS: Final = 2  # [OURS]
SELF_RATING_SD_FLOOR: Final = 1.0  # [OURS] points
SPEED_SD_FLOOR: Final = 0.15  # [OURS] 1/s

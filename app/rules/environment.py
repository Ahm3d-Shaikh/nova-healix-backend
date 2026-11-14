"""E — Hostile / closed environments: CO2 and cabin temperature."""

from app.models.alert import Alert
from app.models.enums import Hazard, Level
from app.rules.context import RuleContext

CO2_7D_LIMIT = 2.5  # mmHg, keeps headache risk <1% (NASA-STD-3001)
CO2_1H_LIMIT = 3.0  # mmHg (NASA-STD-3001 V2 6004)
TEMP_RANGE = (18.0, 27.0)  # °C, NASA ECLSS operating range
SRC_CO2 = "NASA-STD-3001 V2 6004 / NASA OCHMO CO2 brief; readings simulated"
SRC_TEMP = "NASA ECLSS brief (18-27 °C); readings simulated"


def evaluate(ctx: RuleContext) -> list[Alert]:
    r = ctx.records[-1]
    return [_co2(r.co2_mmhg_1h, r.co2_mmhg_7d), _temperature(r.cabin_temp_c)]


def _co2(one_h: float, seven_d: float) -> Alert:
    if one_h > CO2_1H_LIMIT:
        level, action = Level.RED, "Check scrubbers and ventilation now; reduce exertion."
    elif seven_d > CO2_7D_LIMIT:
        level, action = Level.AMBER, "Inspect CO2 removal; watch for headaches."
    else:
        level, action = Level.GREEN, "No action needed."
    return Alert(
        rule="E.co2", hazard=Hazard.ENVIRONMENT, level=level,
        what=f"CO2: 1-h {one_h:.2f} mmHg (limit {CO2_1H_LIMIT:g}), 7-day avg {seven_d:.2f} mmHg (limit {CO2_7D_LIMIT:g}).",
        why="Elevated CO2 causes headaches and degrades performance.",
        action=action, source=SRC_CO2,
    )


def _temperature(temp: float) -> Alert:
    low, high = TEMP_RANGE
    ok = low <= temp <= high
    return Alert(
        rule="E.temperature", hazard=Hazard.ENVIRONMENT,
        level=Level.GREEN if ok else Level.AMBER,
        what=f"Cabin temperature {temp:.1f} °C (range {low:g}-{high:g} °C).",
        why="Out-of-range cabin temperature stresses crew and equipment.",
        action="No action needed." if ok else "Adjust thermal control and check ECLSS.",
        source=SRC_TEMP,
    )

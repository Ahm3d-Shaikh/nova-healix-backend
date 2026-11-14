"""E - Hostile / closed environments: CO2 and cabin temperature."""

from app.models.alert import Alert
from app.models.enums import Hazard, Level
from app.rules import thresholds as t
from app.rules.context import RuleContext

SRC_CO2 = "NASA-STD-3001 V2 6004 / NASA OCHMO CO2 brief; readings simulated"
SRC_TEMP = "NASA ECLSS brief (18-27 °C); readings simulated"


def evaluate(ctx: RuleContext) -> list[Alert]:
    latest = ctx.records[-1]
    return [_co2(latest.co2_mmhg_1h, latest.co2_mmhg_7d), _temperature(latest.cabin_temp_c)]


def _co2(one_h: float, seven_d: float) -> Alert:
    if one_h > t.CO2_1H_LIMIT_MMHG:
        level, action = Level.RED, "Check scrubbers and ventilation now; reduce exertion."
    elif seven_d > t.CO2_7D_LIMIT_MMHG:
        level, action = Level.AMBER, "Inspect CO2 removal; watch for headaches."
    else:
        level, action = Level.GREEN, "No action needed."
    return Alert(
        rule="E.co2",
        hazard=Hazard.ENVIRONMENT,
        level=level,
        what=(
            f"CO2: 1-h {one_h:.2f} mmHg (limit {t.CO2_1H_LIMIT_MMHG:g}), "
            f"7-day avg {seven_d:.2f} mmHg (limit {t.CO2_7D_LIMIT_MMHG:g})."
        ),
        why="Elevated CO2 causes headaches and degrades performance.",
        action=action,
        source=SRC_CO2,
    )


def _temperature(temp: float) -> Alert:
    ok = t.TEMP_MIN_C <= temp <= t.TEMP_MAX_C
    return Alert(
        rule="E.temperature",
        hazard=Hazard.ENVIRONMENT,
        level=Level.GREEN if ok else Level.AMBER,
        what=f"Cabin temperature {temp:.1f} °C (range {t.TEMP_MIN_C:g}-{t.TEMP_MAX_C:g} °C).",
        why="Out-of-range cabin temperature stresses crew and equipment.",
        action="No action needed." if ok else "Adjust thermal control and check ECLSS.",
        source=SRC_TEMP,
    )

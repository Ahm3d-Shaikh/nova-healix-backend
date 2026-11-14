from pydantic import BaseModel, Field, computed_field

from app.models.alert import Alert
from app.models.enums import DataSource, Hazard, Level
from app.models.metrics import CardMetrics


class DailyRecord(BaseModel):
    day: int
    sleep_hours: float
    resting_hr: float
    sys_bp: float
    dia_bp: float
    exercise_min: float
    co2_mmhg_1h: float
    co2_mmhg_7d: float
    cabin_temp_c: float
    loneliness_q1: int = Field(ge=1, le=3)
    loneliness_q2: int = Field(ge=1, le=3)
    loneliness_q3: int = Field(ge=1, le=3)
    self_rating: int = Field(ge=1, le=10)
    pvt_mean_rt: float  # ms
    pvt_mean_speed: float  # mean 1/RT, in 1/s (higher = better)
    pvt_lapses: int
    pvt_false_starts: int
    dose_msv: float
    # Overlay set when an AI check-in scored this day (q1-q3 then come from the rating)
    loneliness_source: str = "simulated"  # "simulated" | "ai_checkin"
    isolation_safety_flag: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def loneliness_total(self) -> int:
        return self.loneliness_q1 + self.loneliness_q2 + self.loneliness_q3


class Astronaut(BaseModel):
    id: str
    name: str
    role: str
    story: str


class CardStatus(BaseModel):
    hazard: Hazard
    label: str
    level: Level
    alerts: list[Alert]  # every rule result for this hazard (green included)
    metrics: CardMetrics  # typed numbers behind the card


class GapPoint(BaseModel):
    day: int
    gap: float | None


class AstronautSummary(BaseModel):
    astronaut: Astronaut
    day: int
    overall: Level
    cards: dict[Hazard, Level]


class CrewDetail(BaseModel):
    astronaut: Astronaut
    day: int
    overall: Level
    cards: list[CardStatus]
    alerts: list[Alert]  # amber / red only
    records: list[DailyRecord]
    mirror_gap_series: list[GapPoint]
    radiation_source: DataSource


class DashboardCrew(BaseModel):
    astronaut: Astronaut
    overall: Level
    cards: list[CardStatus]
    alerts: list[Alert]  # amber / red only

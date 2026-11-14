"""Typed numbers behind each RIDGE card (discriminated by `kind`)."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class RadiationMetrics(BaseModel):
    kind: Literal["radiation"] = "radiation"
    cumulative_dose_msv: float
    career_limit_msv: float
    percent_of_limit: float
    latest_daily_dose_msv: float
    neutron_share_estimate: float
    neutron_dose_estimate_msv: float
    iss_neutron_usv_per_day: float
    sep_events_24h: int
    x_flares_24h: int
    cmes_24h: int
    data_source: str
    data_as_of: str


class IsolationMetrics(BaseModel):
    kind: Literal["isolation"] = "isolation"
    loneliness_score: int
    scale_min: int
    scale_max: int
    consecutive_days_at_or_above_7: int
    history: list[int]


class DistanceMetrics(BaseModel):
    kind: Literal["distance"] = "distance"
    mission: str
    comms_delay: str
    deep_space_mode: bool
    data_source: str
    data_as_of: str


class Vital(BaseModel):
    value: float
    baseline_mean: float | None = None
    threshold: float | None = None  # baseline mean + 2 SD
    above_threshold: bool | None = None


class GravityMetrics(BaseModel):
    kind: Literal["gravity"] = "gravity"
    baseline_ready: bool
    resting_hr: Vital
    sys_bp: Vital
    dia_bp: Vital
    exercise_min: float
    exercise_missed_days: int
    drifting: list[str]


class EnvironmentMetrics(BaseModel):
    kind: Literal["environment"] = "environment"
    co2_mmhg_1h: float
    co2_1h_limit: float
    co2_mmhg_7d: float
    co2_7d_limit: float
    cabin_temp_c: float
    temp_min_c: float
    temp_max_c: float


class MirrorMetrics(BaseModel):
    kind: Literal["mirror"] = "mirror"
    gap: float | None
    amber_gap: float
    red_gap: float
    self_rating: int
    pvt_mean_rt_ms: float
    pvt_lapses: int
    lapse_band: str
    baseline_sessions: int


CardMetrics = Annotated[
    RadiationMetrics | IsolationMetrics | DistanceMetrics | GravityMetrics | EnvironmentMetrics | MirrorMetrics,
    Field(discriminator="kind"),
]

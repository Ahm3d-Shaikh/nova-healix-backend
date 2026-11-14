from pydantic import BaseModel, Field

from app.models.enums import COMMS_DELAY, Mission


class MissionSettings(BaseModel):
    mission: Mission = Mission.MARS
    deep_space_mode: bool = False
    current_day: int = Field(default=5, ge=1)


class MissionSettingsResponse(MissionSettings):
    comms_delay: str
    mission_days: int

    @classmethod
    def build(cls, s: MissionSettings, mission_days: int) -> "MissionSettingsResponse":
        return cls(**s.model_dump(), comms_delay=COMMS_DELAY[s.mission], mission_days=mission_days)

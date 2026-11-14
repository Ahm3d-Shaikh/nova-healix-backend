"""Application settings, loaded from environment variables / `.env`."""

from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "RIDGE Monitor API"
    app_version: str = "2.0.0"
    cors_origins: list[str] = ["http://localhost:4200"]

    # --- NASA DONKI ---------------------------------------------------------
    nasa_api_key: str = "DEMO_KEY"  # DEMO_KEY is heavily rate-limited
    donki_base_url: str = "https://api.nasa.gov/DONKI"
    donki_timeout_seconds: float = 15.0
    donki_cache_ttl_seconds: int = 3600
    donki_snapshot_path: Path = APP_DIR / "data" / "donki_snapshot.json"

    # --- Mission timeline ---------------------------------------------------
    mission_days: int = 30
    # One real DONKI solar episode (May 2024) is inserted into the mission:
    # the first SEP of the episode lands on `storm_day`.
    storm_day: int = 20
    storm_anchor: datetime = datetime(2024, 5, 9, 13, 59, tzinfo=timezone.utc)
    storm_window_start: date = date(2024, 5, 8)
    storm_window_end: date = date(2024, 5, 12)

    # --- Simulation ---------------------------------------------------------
    crew_seed: int = 2026

    @computed_field  # type: ignore[prop-decorator]
    @property
    def mission_start(self) -> datetime:
        """UTC midnight at the start of mission day 1."""
        anchor_midnight = self.storm_anchor.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return anchor_midnight - timedelta(days=self.storm_day - 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()

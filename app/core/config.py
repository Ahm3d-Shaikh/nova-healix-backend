"""Application settings, loaded from environment variables / `.env`."""

from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "RIDGE Monitor API"
    app_version: str = "2.0.0"
    cors_origins: list[str] = ["http://localhost:4200"]
    log_level: str = "INFO"

    # --- NASA DONKI ---------------------------------------------------------
    nasa_api_key: str = "DEMO_KEY"  # DEMO_KEY is heavily rate-limited
    donki_base_url: str = "https://api.nasa.gov/DONKI"
    donki_timeout_seconds: float = 6.0  # per request
    donki_total_timeout_seconds: float = 12.0  # whole refresh, so offline never blocks the UI
    donki_cache_ttl_seconds: int = 3600
    donki_snapshot_path: Path = APP_DIR / "data" / "donki_snapshot.json"

    # --- Persistence (set to empty/None to keep submissions in memory only) --
    submissions_dir: Path | None = Path("var")

    # --- Mission timeline ---------------------------------------------------
    mission_days: int = 30
    # One real DONKI solar episode (May 2024) is inserted into the mission:
    # the first SEP of the episode lands on `storm_day`.
    storm_day: int = 20
    storm_anchor: datetime = datetime(2024, 5, 9, 13, 59, tzinfo=UTC)
    storm_window_start: date = date(2024, 5, 8)
    storm_window_end: date = date(2024, 5, 12)

    # --- Simulation ---------------------------------------------------------
    crew_seed: int = 2026

    @field_validator("submissions_dir", mode="before")
    @classmethod
    def _blank_dir_means_memory_only(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("nasa_api_key")
    @classmethod
    def _blank_key_means_demo(cls, value: str) -> str:
        return value.strip() or "DEMO_KEY"

    @property
    def mission_start(self) -> datetime:
        """UTC midnight at the start of mission day 1."""
        anchor_midnight = self.storm_anchor.replace(hour=0, minute=0, second=0, microsecond=0)
        return anchor_midnight - timedelta(days=self.storm_day - 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()

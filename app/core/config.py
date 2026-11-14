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

    # --- NASA JPL Horizons (distance from Earth) -----------------------------
    horizons_base_url: str = "https://ssd.jpl.nasa.gov/api/horizons.api"
    horizons_timeout_seconds: float = 20.0
    horizons_cache_ttl_seconds: int = 86400  # past ephemerides never change
    horizons_snapshot_path: Path = APP_DIR / "data" / "horizons_snapshot.json"

    # --- Supabase (blank URL/key = in-memory store, data lost on restart) -----
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_timeout_seconds: float = 10.0
    seed_simulated_crew: bool = True  # write the simulated crew to an empty database

    # --- Google Gemini (AI isolation check-in companion) -----------------------
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"  # free tier on the Gemini API
    gemini_timeout_seconds: float = 60.0

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

    @field_validator("nasa_api_key")
    @classmethod
    def _blank_key_means_demo(cls, value: str) -> str:
        return value.strip() or "DEMO_KEY"

    @property
    def use_supabase(self) -> bool:
        return bool(self.supabase_url.strip() and self.supabase_service_role_key.strip())

    @property
    def mission_start(self) -> datetime:
        """UTC midnight at the start of mission day 1."""
        anchor_midnight = self.storm_anchor.replace(hour=0, minute=0, second=0, microsecond=0)
        return anchor_midnight - timedelta(days=self.storm_day - 1)

    @property
    def mission_window(self) -> tuple[date, date]:
        """First and last calendar dates covered by the mission (end of the final day included)."""
        return self.mission_start.date(), (self.mission_start + timedelta(days=self.mission_days)).date()


@lru_cache
def get_settings() -> Settings:
    return Settings()

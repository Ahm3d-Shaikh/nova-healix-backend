"""Application settings, loaded from environment variables / `.env`."""

from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Nova Healix API"
    app_version: str = "3.0.0"
    # Browser origins allowed to call the API: the Angular dev server and the deployed frontend.
    cors_origins: list[str] = ["http://localhost:4200", "https://nova-helix.vercel.app"]
    log_level: str = "INFO"

    # --- Mission clock ------------------------------------------------------------------------
    # Epoch ms of mission hour 0. Blank = anchored so that "now" is mission day 142 (saved in the database
    # on first start so stored hours stay aligned across restarts).
    launch_epoch_ms: int | None = None

    # --- NASA DONKI: the real storm episode replayed on mission day 97 -------------------------
    nasa_api_key: str = "DEMO_KEY"  # DEMO_KEY is heavily rate-limited
    donki_base_url: str = "https://api.nasa.gov/DONKI"
    donki_timeout_seconds: float = 6.0  # per request
    donki_total_timeout_seconds: float = 12.0  # whole refresh, so offline never blocks the API
    donki_cache_ttl_seconds: int = 3600
    donki_snapshot_path: Path = APP_DIR / "data" / "donki_snapshot.json"
    storm_window_start: date = date(2024, 5, 8)
    storm_window_end: date = date(2024, 5, 12)

    # --- NASA JPL Horizons: Earth-Mars distance for the end of the trajectory ------------------
    horizons_base_url: str = "https://ssd.jpl.nasa.gov/api/horizons.api"
    horizons_timeout_seconds: float = 20.0

    # --- Supabase (blank URL/key = in-memory store, data lost on restart) ----------------------
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_timeout_seconds: float = 10.0

    # --- Google Gemini: ECHO (scored check-in chat) and Nova's open-ended replies ----------------
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"  # ECHO scores check-ins (one call per check-in); free tier
    gemini_chat_model: str = "gemini-3.5-flash-lite"  # chat replies: fastest free-tier model (~1 s)
    gemini_chat_timeout_seconds: float = 20.0  # then ECHO retries once on gemini_model, then 503
    gemini_timeout_seconds: float = 60.0
    companion_enabled: bool = True  # false: Nova's reply endpoint returns 503

    @field_validator("launch_epoch_ms", mode="before")
    @classmethod
    def _blank_launch_means_auto(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("nasa_api_key")
    @classmethod
    def _blank_key_means_demo(cls, value: str) -> str:
        return value.strip() or "DEMO_KEY"

    @property
    def use_supabase(self) -> bool:
        return bool(self.supabase_url.strip() and self.supabase_service_role_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()

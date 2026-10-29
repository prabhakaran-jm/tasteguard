from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    qloo_api_key: str = ""
    qloo_base_url: str = "https://hackathon.api.qloo.com"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    port: int = 8765

    near_radius_km: float = 15.0
    # Alternatives must be closer-in; suburbs like Alfornelos fail this gate.
    alt_radius_km: float = 10.0
    far_radius_km: float = 80.0
    name_similarity_threshold: float = 0.72

    anchor_floor: int = 10
    anchor_target: int = 30
    # Relative position among anchors (product policy).
    allow_anchor_percentile: float = 0.40
    # Soft band: within this of the cutoff → ALLOW with a borderline note.
    allow_borderline_band: float = 0.05

    # Live propose/evaluate/repair only (recorded + /health + /presets unlimited).
    # ~30 calls/min ≈ 10 full runs; do not set lower — one live run is 3 calls.
    # With max-instances=2, effective ceiling is up to ~2× (per-process counters).
    daily_call_cap: int = 200
    per_ip_minute_cap: int = 30
    per_ip_hourly_cap: int = 30  # retained for env compatibility; minute cap is enforced
    regenerate_cooldown_seconds: int = 20
    allow_live: bool = True

    http_timeout_seconds: float = 20.0
    http_retries: int = 2
    search_concurrency: int = 4


@lru_cache
def get_settings() -> Settings:
    return Settings()

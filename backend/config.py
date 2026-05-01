"""Application settings — env-var driven, with sensible local defaults.

CLAUDE.md §6: no hardcoded model names, thresholds, or URIs in business code.
Everything routable lives here. Add a default + an entry in .env.example when
introducing a new knob.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    project_id: str = "contactpulse-dev"
    bq_dataset: str = "contactpulse"
    gcs_bucket: str = "contactpulse-audio"

    gemini_flash_model: str = "gemini-2.0-flash"
    gemini_pro_model: str = "gemini-2.0-pro"

    environment: str = "development"
    api_version: str = "0.1.0"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings instance — call this from FastAPI deps."""
    return Settings()

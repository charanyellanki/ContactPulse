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

    # GCP
    project_id: str = "contactpulse-dev"
    gcp_region: str = "us-central1"
    bq_dataset: str = "contactpulse"
    gcs_bucket: str = "contactpulse-audio"
    gcs_evals_bucket: str = "contactpulse-evals"

    # Models — gemini-2.5 family (2.0 IDs were not yet GA on this project at
    # bootstrap time). 2.5-pro is a "thinking" model: it burns ~150-300
    # tokens internally before emitting text, so synthesis max_output_tokens
    # must comfortably exceed the desired reply length.
    gemini_flash_model: str = "gemini-2.5-flash"
    gemini_pro_model: str = "gemini-2.5-pro"

    # Agent pipeline thresholds
    router_confidence_threshold: float = 0.6
    grounding_min_score: float = 0.8
    max_grounding_retries: int = 1

    # Circuit breaker
    circuit_breaker_failure_threshold: int = 3
    circuit_breaker_window_seconds: int = 60

    # DLP
    dlp_enabled: bool = True

    # Voice — STT v2
    stt_location: str = "global"
    stt_model: str = "chirp"
    stt_language_code: str = "en-US"

    # Voice — TTS v1
    tts_voice_name: str = "en-US-Neural2-F"
    tts_language_code: str = "en-US"
    tts_speaking_rate: float = 1.0

    # Voice — request limits
    voice_max_audio_bytes: int = 5_000_000  # ~30s at 128kbps mp3 / ~10s WAV 16k

    # Runtime
    environment: str = "development"
    api_version: str = "0.1.0"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings instance — call this from FastAPI deps."""
    return Settings()

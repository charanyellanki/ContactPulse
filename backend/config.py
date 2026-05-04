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

    # Eval — minimum reranker score for a retrieval result to count as a "hit"
    # in retrieval-hit-rate@k. Tuned for the current synthetic KB; production
    # would re-tune per-corpus.
    retrieval_hit_threshold: float = 0.5

    # Circuit breaker
    circuit_breaker_failure_threshold: int = 3
    circuit_breaker_window_seconds: int = 60

    # DLP
    dlp_enabled: bool = True

    # Live voice (Gemini Live API on Vertex AI). See CLAUDE.md §14.
    # Vertex Live model IDs as of 2026-05 (per-project allowlist applies —
    # check via `curl … publishers/google/models | grep live`):
    #   - "gemini-live-2.5-flash-native-audio"           — current default,
    #     native audio, broadly available, supports the prebuilt-voice catalog.
    #   - "gemini-2.0-flash-live-preview-04-09"          — older preview;
    #     deprecated in many projects.
    gemini_live_model: str = "gemini-live-2.5-flash-native-audio"
    # Live API regional availability is tighter than chat — `us-central1`
    # is supported across all live-capable models.
    gemini_live_region: str = "us-central1"
    # Prebuilt Vertex Live voices (2026-05): Aoede, Charon, Fenrir, Kore, Puck.
    # Aoede is the warmest neutral US English voice for retail CX.
    gemini_live_voice: str = "Aoede"
    gemini_live_language: str = "en-US"
    # Hard ceiling per WebSocket. The Live API itself caps at ~15 minutes;
    # 10 minutes is generous for the demo and bounds the cost surface.
    gemini_live_session_max_seconds: int = 600

    # Runtime
    environment: str = "development"
    api_version: str = "0.1.0"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings instance — call this from FastAPI deps."""
    return Settings()

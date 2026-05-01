"""Speech-to-Text and Text-to-Speech wrappers for the voice channel.

Architecture:
    audio (WAV bytes)
      → Google STT v2 (chirp model)        → utterance text
        → agent_service.handle_turn(...)   → AgentResponse
          → Google TTS v1 (Neural2 voice)  → audio bytes
            → /agent/voice JSON response

Both STT and TTS are wrapped in the LLM circuit breaker so that a transient
provider outage degrades to a clean error rather than a 500. The wrappers
return raw bytes; the route handler is responsible for base64 framing.

CLAUDE.md §6: model names and voice IDs come from `Settings`, never inline.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from functools import lru_cache

from backend.config import get_settings
from backend.llm import circuit_breaker
from backend.llm.client import AgentError

log = logging.getLogger(__name__)

_STT_CIRCUIT = "stt"
_TTS_CIRCUIT = "tts"


@dataclass
class STTResult:
    transcript: str
    confidence: float
    latency_ms: int
    audio_duration_ms: int


@dataclass
class TTSResult:
    audio_bytes: bytes
    latency_ms: int
    voice: str


# ─── Lazy clients (avoid import-time GCP creds requirement for tests) ─────


@lru_cache(maxsize=1)
def _stt_client():  # type: ignore[no-untyped-def]
    from google.cloud import speech_v2  # local import: optional dep

    return speech_v2.SpeechClient()


@lru_cache(maxsize=1)
def _tts_client():  # type: ignore[no-untyped-def]
    from google.cloud import texttospeech_v1  # local import: optional dep

    return texttospeech_v1.TextToSpeechClient()


# ─── STT ──────────────────────────────────────────────────────────────────


def transcribe(audio_bytes: bytes, *, sample_rate_hz: int = 16000) -> STTResult:
    """Transcribe a WAV-encoded utterance using STT v2 with the `chirp` model.

    The audio is expected to be a single-channel WAV. STT v2 auto-detects most
    container formats, so we pass `auto_decoding_config` to avoid hard-coding
    the encoding from the browser MediaRecorder side.
    """
    from google.cloud.speech_v2.types import cloud_speech

    s = get_settings()
    started = time.perf_counter()

    try:
        circuit_breaker.check(_STT_CIRCUIT)
        client = _stt_client()
        recognizer = (
            f"projects/{s.project_id}/locations/{s.stt_location}/recognizers/_"
        )
        config = cloud_speech.RecognitionConfig(
            auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
            language_codes=[s.stt_language_code],
            model=s.stt_model,
        )
        request = cloud_speech.RecognizeRequest(
            recognizer=recognizer,
            config=config,
            content=audio_bytes,
        )
        response = client.recognize(request=request)
        circuit_breaker.record_success(_STT_CIRCUIT)
    except circuit_breaker.CircuitOpenError as exc:
        raise AgentError(f"stt circuit open: {exc}") from exc
    except Exception as exc:
        log.warning("stt failed: %s", exc, exc_info=True)
        circuit_breaker.record_failure(_STT_CIRCUIT)
        raise AgentError(f"stt failed: {exc}") from exc

    if not response.results or not response.results[0].alternatives:
        return STTResult(
            transcript="",
            confidence=0.0,
            latency_ms=int((time.perf_counter() - started) * 1000),
            audio_duration_ms=0,
        )

    parts: list[str] = []
    confidences: list[float] = []
    for r in response.results:
        if r.alternatives:
            parts.append(r.alternatives[0].transcript)
            confidences.append(r.alternatives[0].confidence)

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return STTResult(
        transcript=" ".join(p.strip() for p in parts).strip(),
        confidence=avg_conf,
        latency_ms=int((time.perf_counter() - started) * 1000),
        audio_duration_ms=int(len(audio_bytes) / max(sample_rate_hz, 1) * 500),
    )


# ─── TTS ──────────────────────────────────────────────────────────────────


def synthesize(text: str) -> TTSResult:
    """Render `text` to MP3 audio using a Neural2 US English voice."""
    from google.cloud import texttospeech_v1 as tts

    s = get_settings()
    started = time.perf_counter()

    try:
        circuit_breaker.check(_TTS_CIRCUIT)
        client = _tts_client()
        input_msg = tts.SynthesisInput(text=text)
        voice = tts.VoiceSelectionParams(
            language_code=s.tts_language_code,
            name=s.tts_voice_name,
        )
        audio_config = tts.AudioConfig(
            audio_encoding=tts.AudioEncoding.MP3,
            speaking_rate=s.tts_speaking_rate,
        )
        response = client.synthesize_speech(
            input=input_msg, voice=voice, audio_config=audio_config
        )
        circuit_breaker.record_success(_TTS_CIRCUIT)
    except circuit_breaker.CircuitOpenError as exc:
        raise AgentError(f"tts circuit open: {exc}") from exc
    except Exception as exc:
        log.warning("tts failed: %s", exc, exc_info=True)
        circuit_breaker.record_failure(_TTS_CIRCUIT)
        raise AgentError(f"tts failed: {exc}") from exc

    return TTSResult(
        audio_bytes=response.audio_content,
        latency_ms=int((time.perf_counter() - started) * 1000),
        voice=s.tts_voice_name,
    )

"""Cloud DLP de-identification at the pipeline boundary.

Calls Google Cloud DLP `deidentify_content` with a small set of InfoTypes
relevant to retail CX. Wrapped in the circuit breaker so a DLP outage does
not take down customer turns — we degrade to a regex fallback and surface
that in the trace.

InfoTypes covered:
  PERSON_NAME, PHONE_NUMBER, EMAIL_ADDRESS, STREET_ADDRESS, CREDIT_CARD_NUMBER

CLAUDE.md §10 #11: trust nothing. PII redaction runs BEFORE the utterance
ever reaches the router, the synthesizer, or any prompt template.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache

from backend.config import get_settings
from backend.llm import circuit_breaker

log = logging.getLogger(__name__)

_DLP_CIRCUIT = "dlp"

_INFO_TYPES: list[str] = [
    "PERSON_NAME",
    "PHONE_NUMBER",
    "EMAIL_ADDRESS",
    "STREET_ADDRESS",
    "CREDIT_CARD_NUMBER",
]

# Last-resort regex fallback used when DLP is disabled or its circuit is open.
# Deliberately conservative — we'd rather under-redact in fallback (and rely
# on the verifier + escalation paths) than corrupt legitimate inputs.
_FALLBACK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b"),                "[PHONE_NUMBER]"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),                     "[EMAIL_ADDRESS]"),
    (re.compile(r"\b(?:\d[ -]*?){13,16}\b"),                          "[CREDIT_CARD_NUMBER]"),
]


@dataclass
class DeidResult:
    text: str
    redacted: bool
    method: str  # "cloud_dlp" | "regex_fallback" | "noop"


@lru_cache(maxsize=1)
def _dlp_client():  # type: ignore[no-untyped-def]
    """Lazy import — keeps test environments without google-cloud-dlp working
    as long as DLP_ENABLED=false."""
    from google.cloud import dlp_v2

    return dlp_v2.DlpServiceClient()


def _deidentify_with_cloud_dlp(text: str) -> DeidResult:
    from google.cloud import dlp_v2

    settings = get_settings()
    parent = f"projects/{settings.project_id}/locations/{settings.gcp_region}"
    client = _dlp_client()

    inspect_config = {
        "info_types": [{"name": t} for t in _INFO_TYPES],
        "min_likelihood": dlp_v2.Likelihood.POSSIBLE,
    }
    deidentify_config = {
        "info_type_transformations": {
            "transformations": [
                {
                    "primitive_transformation": {
                        "replace_with_info_type_config": {}
                    }
                }
            ]
        }
    }
    response = client.deidentify_content(
        request={
            "parent": parent,
            "inspect_config": inspect_config,
            "deidentify_config": deidentify_config,
            "item": {"value": text},
        }
    )
    redacted_text = response.item.value
    return DeidResult(
        text=redacted_text,
        redacted=redacted_text != text,
        method="cloud_dlp",
    )


def _fallback_regex(text: str) -> DeidResult:
    out = text
    redacted = False
    for pattern, replacement in _FALLBACK_PATTERNS:
        new = pattern.sub(replacement, out)
        if new != out:
            redacted = True
            out = new
    return DeidResult(text=out, redacted=redacted, method="regex_fallback")


class DlpService:
    """De-identification at the input boundary."""

    def deidentify(self, text: str) -> DeidResult:
        if not text:
            return DeidResult(text=text, redacted=False, method="noop")
        if not get_settings().dlp_enabled:
            return _fallback_regex(text)
        try:
            circuit_breaker.check(_DLP_CIRCUIT)
            result = _deidentify_with_cloud_dlp(text)
            circuit_breaker.record_success(_DLP_CIRCUIT)
            return result
        except circuit_breaker.CircuitOpenError:
            log.warning("dlp circuit open — falling back to regex")
            return _fallback_regex(text)
        except Exception:
            log.exception("cloud dlp call failed — falling back to regex")
            circuit_breaker.record_failure(_DLP_CIRCUIT)
            return _fallback_regex(text)


@lru_cache(maxsize=1)
def get_dlp_service() -> DlpService:
    return DlpService()

"""Vertex AI Gemini client wrapper.

CLAUDE.md §6: all LLM calls go through this module — no direct Vertex/Gemini
client instantiation elsewhere. Every call is wrapped in the circuit breaker
and returns a structured result so the orchestrator can log a TraceEvent.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import vertexai
from vertexai.generative_models import GenerationConfig, GenerativeModel

from backend.config import get_settings
from backend.llm import circuit_breaker

log = logging.getLogger(__name__)

# Per-1k-token prices (USD) — back-of-envelope, gemini-2.5 list pricing.
# Used only for trace logging so the Operator Console can surface
# cost-per-call. Keep in sync with ARCHITECTURE.md §12.
_PRICE_PER_1K_INPUT = {
    "flash": 0.0003,    # gemini-2.5-flash
    "pro":   0.00125,   # gemini-2.5-pro (≤200k context)
}
_PRICE_PER_1K_OUTPUT = {
    "flash": 0.0025,
    "pro":   0.01,
}


class AgentError(RuntimeError):
    """Raised when an LLM call fails after retries / circuit is open."""


@dataclass
class LLMResult:
    """One LLM call's outcome — the orchestrator stores this on each TraceEvent."""

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost_usd: float


_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


@lru_cache(maxsize=8)
def load_prompt(name: str) -> str:
    """Load a prompt template from `backend/prompts/<name>.txt`. Cached.

    CLAUDE.md §6: prompts live on disk, never inlined in agent code.
    """
    path = _PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"prompt template not found: {path}")
    return path.read_text(encoding="utf-8")


def render(template: str, **vars: str) -> str:
    """Tiny `{{KEY}}` substitution. Avoids pulling Jinja for three placeholders."""
    out = template
    for k, v in vars.items():
        out = out.replace("{{" + k + "}}", v)
    return out


@lru_cache(maxsize=1)
def _vertex_init() -> None:
    s = get_settings()
    vertexai.init(project=s.project_id, location=s.gcp_region)


@lru_cache(maxsize=4)
def _model(model_name: str) -> GenerativeModel:
    _vertex_init()
    return GenerativeModel(model_name)


def _model_class(model_name: str) -> str:
    """`flash` vs `pro` for the cost table."""
    return "flash" if "flash" in model_name.lower() else "pro"


def _estimate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    cls = _model_class(model_name)
    return (
        input_tokens  / 1000.0 * _PRICE_PER_1K_INPUT[cls]
        + output_tokens / 1000.0 * _PRICE_PER_1K_OUTPUT[cls]
    )


def _circuit_name(model_name: str) -> str:
    return f"gemini_{_model_class(model_name)}"


def generate(
    *,
    model: str,
    prompt: str,
    temperature: float = 0.2,
    max_output_tokens: int = 512,
    response_mime_type: str | None = None,
    timeout_s: float | None = 60.0,
) -> LLMResult:
    """Single Gemini call. Returns LLMResult; raises AgentError on failure.

    `response_mime_type="application/json"` activates Vertex's JSON-mode where
    available; we fall back to lenient parsing in `generate_json` either way.

    `timeout_s` is currently a no-op — the installed `vertexai` SDK
    (`google-cloud-aiplatform`) does not accept a per-call `request_options`
    kwarg on `generate_content`. The parameter is retained in the signature
    so callers don't break; if the SDK gains support we wire it up here. The
    circuit breaker still bounds total exposure.
    """
    name = _circuit_name(model)
    circuit_breaker.check(name)

    try:
        gm = _model(model)
        cfg_kwargs: dict = {
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        }
        if response_mime_type is not None:
            cfg_kwargs["response_mime_type"] = response_mime_type
        cfg = GenerationConfig(**cfg_kwargs)

        t0 = time.perf_counter()
        resp = gm.generate_content(prompt, generation_config=cfg)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        text = (resp.text or "").strip() if hasattr(resp, "text") else ""
        usage = getattr(resp, "usage_metadata", None)
        in_tok = int(getattr(usage, "prompt_token_count", 0) or 0)
        out_tok = int(getattr(usage, "candidates_token_count", 0) or 0)

        circuit_breaker.record_success(name)
        return LLMResult(
            text=text,
            model=model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            latency_ms=latency_ms,
            cost_usd=_estimate_cost(model, in_tok, out_tok),
        )
    except circuit_breaker.CircuitOpenError:
        raise
    except Exception as exc:
        circuit_breaker.record_failure(name)
        log.exception("gemini call failed model=%s", model)
        raise AgentError(f"gemini call failed: {exc}") from exc


_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_json_lenient(text: str) -> dict:
    """Best-effort JSON extraction. Models occasionally wrap output in fences
    or trailing commentary even when asked not to — strip and retry once."""
    candidate = text.strip()
    # Strip ```json ... ``` fences if present
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.lower().startswith("json"):
            candidate = candidate[4:]
        candidate = candidate.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        m = _JSON_OBJ_RE.search(candidate)
        if not m:
            raise AgentError(f"could not parse JSON from model output: {text!r}")
        return json.loads(m.group(0))


def generate_json(
    *,
    model: str,
    prompt: str,
    temperature: float = 0.1,
    max_output_tokens: int = 512,
    timeout_s: float | None = 60.0,
) -> tuple[dict, LLMResult]:
    """Generate + parse JSON. Returns (parsed_dict, llm_result)."""
    result = generate(
        model=model,
        prompt=prompt,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        response_mime_type="application/json",
        timeout_s=timeout_s,
    )
    try:
        parsed = parse_json_lenient(result.text)
    except (AgentError, json.JSONDecodeError) as exc:
        raise AgentError(f"model returned non-JSON: {result.text!r}") from exc
    return parsed, result

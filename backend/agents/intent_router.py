"""Intent router (Gemini 2.0 Flash).

Classifies the customer utterance into one of:
  order_status | product_qa | service_request | escalation | out_of_scope

Returns an IntentResult with confidence, the journey (the routable subset),
and a `needs_escalation` boolean. The orchestrator handles confidence
gating and escalation short-circuits.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from backend.config import get_settings
from backend.llm.client import LLMResult, generate_json, load_prompt, render

log = logging.getLogger(__name__)

Intent = Literal[
    "order_status",
    "product_qa",
    "service_request",
    "escalation",
    "out_of_scope",
]
Journey = Literal["order_status", "product_qa", "service_request"]

_VALID_INTENTS: set[str] = {
    "order_status",
    "product_qa",
    "service_request",
    "escalation",
    "out_of_scope",
}


@dataclass
class IntentResult:
    intent: Intent
    confidence: float
    journey: Journey | None
    needs_escalation: bool
    reasoning: str
    llm: LLMResult


def _format_history(history: list[dict]) -> str:
    if not history:
        return "(no prior turns)"
    lines = []
    for h in history:
        role = h.get("role", "user")
        text = h.get("text", "")
        lines.append(f"{role}: {text}")
    return "\n".join(lines)


def classify(utterance: str, history: list[dict]) -> IntentResult:
    """Classify intent. Raises AgentError on Gemini failure (per spec)."""
    settings = get_settings()
    template = load_prompt("intent_router")
    prompt = render(
        template,
        HISTORY=_format_history(history),
        UTTERANCE=utterance,
    )

    parsed, llm = generate_json(
        model=settings.gemini_flash_model,
        prompt=prompt,
        temperature=0.0,
        # Headroom for any thinking-token overhead on 2.5-flash.
        max_output_tokens=512,
    )

    raw_intent = str(parsed.get("intent", "")).strip()
    confidence = float(parsed.get("confidence", 0.0))
    reasoning = str(parsed.get("reasoning", ""))

    if raw_intent not in _VALID_INTENTS:
        log.warning("router returned unknown intent %r — coercing to out_of_scope", raw_intent)
        raw_intent = "out_of_scope"
        confidence = min(confidence, 0.4)

    intent: Intent = raw_intent  # type: ignore[assignment]

    journey: Journey | None
    if intent in {"order_status", "product_qa", "service_request"}:
        journey = intent  # type: ignore[assignment]
    else:
        journey = None

    needs_escalation = intent == "escalation"

    return IntentResult(
        intent=intent,
        confidence=max(0.0, min(1.0, confidence)),
        journey=journey,
        needs_escalation=needs_escalation,
        reasoning=reasoning,
        llm=llm,
    )

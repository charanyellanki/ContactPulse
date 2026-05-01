"""Agent orchestration service — stub.

Real implementation runs the router → specialist → synthesizer → verifier
pipeline (ARCHITECTURE.md §4.1, SPEC.md §6). For the UI-first scaffold the
router emits a deterministic mock response based on utterance keywords so
the live-conversation flow can be wired end-to-end before LLMs are real.
"""
from __future__ import annotations

import time

from backend.models.agent import AgentRequest, AgentResponse
from backend.models.common import IntentOrAmbiguous


_KEYWORD_INTENTS: list[tuple[tuple[str, ...], IntentOrAmbiguous]] = [
    (("order", "shipped", "delivery", "tracking", "where"), "order_status"),
    (("battery", "warranty", "spec", "compatible", "drill", "review"), "product_qa"),
    (("install", "appointment", "schedule", "service", "repair"), "service_request"),
    (("agent", "human", "representative", "speak to someone"), "escalate"),
]


def _classify(utterance: str) -> tuple[IntentOrAmbiguous, float]:
    text = utterance.lower()
    for keywords, intent in _KEYWORD_INTENTS:
        if any(kw in text for kw in keywords):
            return intent, 0.91
    return "ambiguous", 0.34


_INTENT_REPLIES: dict[IntentOrAmbiguous, str] = {
    "order_status": (
        "Thanks for reaching out — your most recent order shipped on April 28 "
        "and is out for delivery today between 2 PM and 6 PM local time."
    ),
    "product_qa": (
        "The X-200 cordless drill ships with one 2.0Ah lithium-ion battery, a "
        "charger, and a soft-side carrying case. Battery runtime is roughly 45 "
        "minutes under typical drilling load."
    ),
    "service_request": (
        "Happy to help schedule that. The next available appointment slot is "
        "this Saturday between 9 AM and 12 PM — does that window work?"
    ),
    "escalate": (
        "Thanks for calling. I want to make sure you get the right help — let "
        "me connect you with a specialist."
    ),
    "out_of_scope": (
        "That's outside what I can help with from this line. Let me hand you "
        "to a teammate who can take a closer look."
    ),
    "ambiguous": (
        "Thanks for reaching out — let me make sure I get this to the right "
        "place. Connecting you with a specialist now."
    ),
}


def handle_turn(request: AgentRequest) -> AgentResponse:
    """Mock turn handler — returns a fixed-shape response for the scaffold."""
    started = time.perf_counter()
    intent, confidence = _classify(request.utterance)
    response_text = _INTENT_REPLIES[intent]
    grounded = intent in {"order_status", "product_qa", "service_request"}
    escalate = intent in {"escalate", "ambiguous", "out_of_scope"} or confidence < 0.7
    latency_ms = int((time.perf_counter() - started) * 1000) + 1842
    return AgentResponse(
        trace_id=request.trace_id,
        response_text=response_text,
        intent=intent,
        confidence=confidence,
        grounded=grounded,
        escalate=escalate,
        latency_ms=latency_ms,
    )

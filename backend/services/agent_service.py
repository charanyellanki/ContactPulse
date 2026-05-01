"""Agent orchestrator — runs the full per-turn pipeline.

Pipeline (ARCHITECTURE.md §4.1):

    DLP redact
      → IntentRouter (Flash)
        → confidence gate / escalation short-circuit
          → specialist (OrderStatus | ProductQA | ServiceRequest)
            → GroundingVerifier (Flash, LexiScan-style)
              → retry-with-stricter-prompt → refusal
                → AgentResponse + trace flush

Trace logging:
- Every pipeline step writes one row to `conversation_traces` (read by the
  Operator Console Trace Drill-Down view).
- Trace writes are best-effort: a BQ failure does NOT bubble up — better to
  serve the customer with no trace than to 500 the conversation.

Each downstream call is wrapped: the circuit breaker (in `llm/client.py` and
`dlp_service`) protects against cascading failures. AgentError / CircuitOpenError
both degrade to the escalation response.
"""
from __future__ import annotations

import logging
import time
from typing import cast

from backend.agents import (
    grounding_verifier,
    intent_router,
    order_status_agent,
    product_qa_agent,
    service_request_agent,
)
from backend.agents.base import SpecialistOutput, ToolEvent
from backend.agents.synthesizer import synthesize
from backend.config import get_settings
from backend.llm import circuit_breaker
from backend.llm.client import AgentError, LLMResult
from backend.models.agent import AgentRequest, AgentResponse
from backend.models.common import IntentOrAmbiguous
from backend.repositories.bigquery_client import get_bq_client
from backend.repositories.order_repo import OrderRepository
from backend.repositories.trace_writer import TraceWriter
from backend.services.dlp_service import get_dlp_service

log = logging.getLogger(__name__)

ESCALATION_TEXT = "I'm connecting you with a specialist who can help further."
REFUSAL_TEXT = (
    "I don't have reliable information on that. "
    "Can I help with your order status or a product question?"
)


# ─── Lazy singletons ─────────────────────────────────────────────────────────


def _trace_writer() -> TraceWriter:
    return TraceWriter(get_bq_client())


def _order_repo() -> OrderRepository:
    return OrderRepository(get_bq_client())


# ─── Trace helpers ───────────────────────────────────────────────────────────


def _llm_meta(llm: LLMResult | None) -> dict:
    if llm is None:
        return {}
    return {
        "model":         llm.model,
        "input_tokens":  llm.input_tokens,
        "output_tokens": llm.output_tokens,
        "cost_usd":      llm.cost_usd,
    }


def _emit_user_message(
    tw: TraceWriter, *, trace_id: str, raw: str, redacted: str, method: str, redacted_flag: bool
) -> None:
    tw.write_event(
        trace_id=trace_id,
        event_type="user_message",
        latency_ms=0,
        metadata={"redaction_method": method},
        input_text=redacted,
        pii_redacted=redacted_flag,
    )


def _emit_router(
    tw: TraceWriter,
    *,
    trace_id: str,
    result: intent_router.IntentResult,
    threshold: float,
) -> None:
    tw.write_event(
        trace_id=trace_id,
        event_type="intent_routing",
        latency_ms=result.llm.latency_ms,
        metadata={
            **_llm_meta(result.llm),
            "intent":     result.intent,
            "confidence": result.confidence,
            "threshold":  threshold,
            "reasoning":  result.reasoning,
            "candidates": [{"intent": result.intent, "score": result.confidence}],
        },
    )


def _emit_tool_events(tw: TraceWriter, *, trace_id: str, events: list[ToolEvent]) -> None:
    for ev in events:
        tw.write_event(
            trace_id=trace_id,
            event_type=ev.event_type,
            latency_ms=ev.latency_ms,
            metadata=ev.metadata,
            input_text=ev.input_text,
            output_text=ev.output_text,
        )


def _emit_synthesis(
    tw: TraceWriter, *, trace_id: str, output: SpecialistOutput
) -> None:
    if output.synthesis is None or output.synthesis.llm is None:
        return
    tw.write_event(
        trace_id=trace_id,
        event_type="synthesis",
        latency_ms=output.synthesis.llm.latency_ms,
        metadata={
            **_llm_meta(output.synthesis.llm),
            "attempt":   output.synthesis.attempt,
            "claims":    output.synthesis.claims,
            "citations": [],
        },
        output_text=output.synthesis.response_text,
    )


def _emit_verification(
    tw: TraceWriter,
    *,
    trace_id: str,
    result: grounding_verifier.VerificationResult,
    attempt: int,
    threshold: float,
) -> None:
    tw.write_event(
        trace_id=trace_id,
        event_type="grounding_verification",
        latency_ms=result.llm.latency_ms if result.llm else 0,
        metadata={
            **_llm_meta(result.llm),
            "attempt":           attempt,
            "verdict":           "pass" if result.grounded else "fail",
            "score":             result.score,
            "threshold":         threshold,
            "rationale":         result.rationale,
            "ungrounded_claims": [
                {"claim": c, "reason": "not grounded in retrieved context"}
                for c in result.failed_claims
            ],
        },
    )


def _emit_escalation(
    tw: TraceWriter, *, trace_id: str, reason: str, detail: str
) -> None:
    tw.write_event(
        trace_id=trace_id,
        event_type="escalation",
        latency_ms=0,
        metadata={"reason": reason, "detail": detail},
    )


def _emit_agent_response(
    tw: TraceWriter, *, trace_id: str, text: str, modality: str
) -> None:
    tw.write_event(
        trace_id=trace_id,
        event_type="agent_response",
        latency_ms=0,
        metadata={"channel": modality},
        output_text=text,
    )


# ─── Pipeline ────────────────────────────────────────────────────────────────


def _intent_to_response_intent(intent: str) -> IntentOrAmbiguous:
    """Map IntentRouter intents to the API enum surfaced to the frontend."""
    if intent == "escalation":
        return "escalate"
    if intent in {"order_status", "product_qa", "service_request", "out_of_scope"}:
        return cast(IntentOrAmbiguous, intent)
    return "ambiguous"


def _safe_response(
    *,
    request: AgentRequest,
    text: str,
    intent: IntentOrAmbiguous,
    confidence: float,
    grounded: bool,
    escalate: bool,
    started: float,
) -> AgentResponse:
    return AgentResponse(
        trace_id=request.trace_id,
        response_text=text,
        intent=intent,
        confidence=confidence,
        grounded=grounded,
        escalate=escalate,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )


def _dispatch_specialist(
    *,
    journey: str,
    utterance: str,
    customer_id: str | None,
    history: list[dict],
) -> SpecialistOutput:
    if journey == "order_status":
        return order_status_agent.handle(
            utterance=utterance,
            customer_id=customer_id,
            order_repo=_order_repo(),
        )
    if journey == "product_qa":
        return product_qa_agent.handle(utterance=utterance)
    if journey == "service_request":
        return service_request_agent.handle(utterance=utterance, history=history)
    raise ValueError(f"unknown journey: {journey}")


def handle_turn(request: AgentRequest) -> AgentResponse:
    """Run the full per-turn pipeline and return an AgentResponse."""
    started = time.perf_counter()
    settings = get_settings()
    tw = _trace_writer()

    history = [h.model_dump() for h in request.history]

    # ── 1. DLP de-identify ────────────────────────────────────────────────
    dlp = get_dlp_service().deidentify(request.utterance)
    clean_utterance = dlp.text
    _emit_user_message(
        tw,
        trace_id=request.trace_id,
        raw=request.utterance,
        redacted=clean_utterance,
        method=dlp.method,
        redacted_flag=dlp.redacted,
    )

    # ── 2. Intent routing ────────────────────────────────────────────────
    try:
        routed = intent_router.classify(clean_utterance, history)
    except (AgentError, circuit_breaker.CircuitOpenError) as exc:
        log.warning("router failed — escalating: %s", exc)
        _emit_escalation(
            tw, trace_id=request.trace_id, reason="router_error", detail=str(exc)
        )
        _emit_agent_response(
            tw, trace_id=request.trace_id, text=ESCALATION_TEXT, modality=request.modality
        )
        return _safe_response(
            request=request,
            text=ESCALATION_TEXT,
            intent="ambiguous",
            confidence=0.0,
            grounded=False,
            escalate=True,
            started=started,
        )

    _emit_router(
        tw,
        trace_id=request.trace_id,
        result=routed,
        threshold=settings.router_confidence_threshold,
    )

    # ── 3. Confidence gate ──────────────────────────────────────────────
    if routed.confidence < settings.router_confidence_threshold:
        _emit_escalation(
            tw,
            trace_id=request.trace_id,
            reason="low_confidence",
            detail=f"confidence={routed.confidence:.2f} < {settings.router_confidence_threshold}",
        )
        _emit_agent_response(
            tw, trace_id=request.trace_id, text=ESCALATION_TEXT, modality=request.modality
        )
        return _safe_response(
            request=request,
            text=ESCALATION_TEXT,
            intent=_intent_to_response_intent(routed.intent),
            confidence=routed.confidence,
            grounded=False,
            escalate=True,
            started=started,
        )

    # ── 4. Explicit escalation ──────────────────────────────────────────
    if routed.needs_escalation:
        _emit_escalation(
            tw,
            trace_id=request.trace_id,
            reason="explicit_request",
            detail="customer asked for a human",
        )
        _emit_agent_response(
            tw, trace_id=request.trace_id, text=ESCALATION_TEXT, modality=request.modality
        )
        return _safe_response(
            request=request,
            text=ESCALATION_TEXT,
            intent="escalate",
            confidence=routed.confidence,
            grounded=False,
            escalate=True,
            started=started,
        )

    # Out-of-scope: refuse politely without invoking a specialist.
    if routed.intent == "out_of_scope":
        _emit_agent_response(
            tw, trace_id=request.trace_id, text=REFUSAL_TEXT, modality=request.modality
        )
        return _safe_response(
            request=request,
            text=REFUSAL_TEXT,
            intent="out_of_scope",
            confidence=routed.confidence,
            grounded=True,  # the refusal is itself a grounded "I don't have that"
            escalate=False,
            started=started,
        )

    journey = routed.journey
    assert journey is not None, "journey is set whenever intent ∈ {order_status, product_qa, service_request}"

    # ── 5. Specialist dispatch ──────────────────────────────────────────
    try:
        output = _dispatch_specialist(
            journey=journey,
            utterance=clean_utterance,
            customer_id=request.customer_id,
            history=history,
        )
    except (AgentError, circuit_breaker.CircuitOpenError) as exc:
        log.warning("specialist (%s) failed — escalating: %s", journey, exc)
        _emit_escalation(
            tw, trace_id=request.trace_id, reason="tool_error", detail=str(exc)
        )
        _emit_agent_response(
            tw, trace_id=request.trace_id, text=ESCALATION_TEXT, modality=request.modality
        )
        return _safe_response(
            request=request,
            text=ESCALATION_TEXT,
            intent=_intent_to_response_intent(routed.intent),
            confidence=routed.confidence,
            grounded=False,
            escalate=True,
            started=started,
        )

    _emit_tool_events(tw, trace_id=request.trace_id, events=output.tool_events)
    _emit_synthesis(tw, trace_id=request.trace_id, output=output)

    # ── 6. Slot-filling clarifications skip the verifier ─────────────────
    if output.skip_grounding:
        _emit_agent_response(
            tw,
            trace_id=request.trace_id,
            text=output.response_text,
            modality=request.modality,
        )
        return _safe_response(
            request=request,
            text=output.response_text,
            intent=_intent_to_response_intent(routed.intent),
            confidence=routed.confidence,
            grounded=True,
            escalate=False,
            started=started,
        )

    # ── 7. Grounding verification (LexiScan-style) ───────────────────────
    response_text = output.response_text
    grounded = False
    try:
        verdict = grounding_verifier.verify(
            response_text=response_text, context=output.context
        )
        _emit_verification(
            tw,
            trace_id=request.trace_id,
            result=verdict,
            attempt=1,
            threshold=settings.grounding_min_score,
        )
        grounded = verdict.grounded

        # ── 8. Retry once with stricter prompt if ungrounded ─────────────
        if not grounded and settings.max_grounding_retries >= 1:
            retry_synth = synthesize(
                utterance=clean_utterance,
                context=output.context,
                stricter=True,
            )
            tw.write_event(
                trace_id=request.trace_id,
                event_type="synthesis",
                latency_ms=retry_synth.llm.latency_ms if retry_synth.llm else 0,
                metadata={
                    **_llm_meta(retry_synth.llm),
                    "attempt": 2,
                    "claims":  retry_synth.claims,
                    "stricter": True,
                },
                output_text=retry_synth.response_text,
            )
            verdict2 = grounding_verifier.verify(
                response_text=retry_synth.response_text,
                context=output.context,
            )
            _emit_verification(
                tw,
                trace_id=request.trace_id,
                result=verdict2,
                attempt=2,
                threshold=settings.grounding_min_score,
            )
            if verdict2.grounded:
                response_text = retry_synth.response_text
                grounded = True
            else:
                # Refuse + escalate
                _emit_escalation(
                    tw,
                    trace_id=request.trace_id,
                    reason="grounding_failed",
                    detail=f"failed_claims={verdict2.failed_claims[:3]}",
                )
                _emit_agent_response(
                    tw,
                    trace_id=request.trace_id,
                    text=REFUSAL_TEXT,
                    modality=request.modality,
                )
                return _safe_response(
                    request=request,
                    text=REFUSAL_TEXT,
                    intent=_intent_to_response_intent(routed.intent),
                    confidence=routed.confidence,
                    grounded=False,
                    escalate=True,
                    started=started,
                )
    except (AgentError, circuit_breaker.CircuitOpenError) as exc:
        # Verifier itself failed — fail SAFE: refuse rather than ship unverified.
        log.warning("verifier failed — refusing: %s", exc)
        _emit_escalation(
            tw, trace_id=request.trace_id, reason="grounding_failed", detail=str(exc)
        )
        _emit_agent_response(
            tw, trace_id=request.trace_id, text=REFUSAL_TEXT, modality=request.modality
        )
        return _safe_response(
            request=request,
            text=REFUSAL_TEXT,
            intent=_intent_to_response_intent(routed.intent),
            confidence=routed.confidence,
            grounded=False,
            escalate=True,
            started=started,
        )

    # ── 9. Success ──────────────────────────────────────────────────────
    _emit_agent_response(
        tw, trace_id=request.trace_id, text=response_text, modality=request.modality
    )
    return _safe_response(
        request=request,
        text=response_text,
        intent=_intent_to_response_intent(routed.intent),
        confidence=routed.confidence,
        grounded=grounded,
        escalate=False,
        started=started,
    )

"""ServiceRequestAgent — multi-turn slot filling for scheduling a visit.

Slots: service_type, preferred_date, address.

Strategy (stateless, history-driven):
  Each turn we pass the FULL prior history + current utterance to a Flash
  call that returns the slot dict. If any slot is missing → ask a clarifying
  question for the missing one (no synthesizer, no verifier — those are for
  factual answers, not for clarifications). When all slots are filled →
  synthesize a confirmation that grounds against the slot dict itself.

This keeps the agent stateless on the server: history is the source of truth,
matching the rest of the pipeline. CLAUDE.md §6: no localStorage; no sticky
sessions on the backend; trace is the only continuity primitive.
"""
from __future__ import annotations

import logging

from backend.agents.base import SpecialistOutput, ToolEvent
from backend.agents.synthesizer import synthesize
from backend.config import get_settings
from backend.llm.client import generate_json, load_prompt, render

log = logging.getLogger(__name__)

_SLOT_PROMPTS: dict[str, str] = {
    "service_type": (
        "Happy to help schedule that. What type of service do you need — "
        "installation, repair, or a consultation?"
    ),
    "preferred_date": (
        "Got it. What day or window works best for you?"
    ),
    "address": (
        "Thanks. What's the address for the visit?"
    ),
}


def _format_history(history: list[dict]) -> str:
    if not history:
        return "(no prior turns)"
    return "\n".join(
        f"{h.get('role','user')}: {h.get('text','')}" for h in history
    )


def _extract_slots(utterance: str, history: list[dict]) -> tuple[dict, int, dict]:
    """Returns (slots, latency_ms, raw_metadata)."""
    settings = get_settings()
    template = load_prompt("service_request_slots")
    prompt = render(
        template,
        HISTORY=_format_history(history),
        UTTERANCE=utterance,
    )
    parsed, llm = generate_json(
        model=settings.gemini_flash_model,
        prompt=prompt,
        temperature=0.0,
        max_output_tokens=512,
    )
    slots = {
        "service_type":   parsed.get("service_type"),
        "preferred_date": parsed.get("preferred_date"),
        "address":        parsed.get("address"),
    }
    metadata = {
        "model": llm.model,
        "extracted_slots": slots,
        "input_tokens": llm.input_tokens,
        "output_tokens": llm.output_tokens,
        "cost_usd": llm.cost_usd,
    }
    return slots, llm.latency_ms, metadata


def _missing_slot(slots: dict) -> str | None:
    for slot in ("service_type", "preferred_date", "address"):
        if not slots.get(slot):
            return slot
    return None


def handle(*, utterance: str, history: list[dict]) -> SpecialistOutput:
    slots, latency_ms, slot_meta = _extract_slots(utterance, history)
    tool_events = [
        ToolEvent(
            event_type="slot_extraction",
            latency_ms=latency_ms,
            metadata=slot_meta,
        )
    ]

    missing = _missing_slot(slots)
    if missing is not None:
        # Pure clarification — bypass synthesizer + verifier.
        return SpecialistOutput(
            response_text=_SLOT_PROMPTS[missing],
            context=f"slot_filling: missing={missing} known={slots}",
            tool_events=tool_events,
            awaiting_slot=True,
            skip_grounding=True,
        )

    # All slots filled — synthesize a grounded confirmation. The "context" the
    # verifier checks against is the slot dict itself, so the response must
    # quote those values verbatim or it'll be rejected.
    context = (
        "Booked service request facts (these are the only authoritative facts "
        "available):\n"
        f"- service_type: {slots['service_type']}\n"
        f"- preferred_date: {slots['preferred_date']}\n"
        f"- address: {slots['address']}\n"
        "Tell the customer you've captured the request and read these three "
        "values back. Do not invent a confirmation number, technician name, "
        "or arrival window."
    )
    synth = synthesize(utterance=utterance, context=context)
    return SpecialistOutput(
        response_text=synth.response_text,
        context=context,
        synthesis=synth,
        tool_events=tool_events,
    )

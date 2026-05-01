"""Specialist agent base types.

Each specialist returns a `SpecialistOutput` with:
  - response_text:   what to say to the customer
  - context:         the prompt context the synthesizer used (verifier sees same)
  - synthesis_llm:   LLMResult for the synthesizer call (for trace logging)
  - tool_events:     repository / retrieval traces (one entry per tool call)
  - awaiting_slot:   set when slot-filling needs another customer turn
  - skip_grounding:  pure clarifying questions don't need a verifier pass

The orchestrator drives the pipeline; agents stay narrow and testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from backend.agents.synthesizer import SynthesisResult
from backend.llm.client import LLMResult


@dataclass
class ToolEvent:
    """A single repository / retrieval call inside a specialist."""

    event_type: str  # "retrieval" | "order_lookup" | "slot_extraction"
    latency_ms: int
    metadata: dict
    input_text: str | None = None
    output_text: str | None = None


@dataclass
class SpecialistOutput:
    response_text: str
    context: str
    synthesis: SynthesisResult | None = None
    tool_events: list[ToolEvent] = field(default_factory=list)
    awaiting_slot: bool = False
    skip_grounding: bool = False
    extra_llm_calls: list[LLMResult] = field(default_factory=list)

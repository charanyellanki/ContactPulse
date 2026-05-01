"""ProductQAAgent — answers product/policy questions over a (stubbed) KB.

Vertex AI Search isn't wired up yet (out of scope for this slice), so we
serve from a small in-memory KB. Shape matches the future Vertex Search
response so swapping in the real retriever is a one-method change.

The retrieval result is the synthesizer's authoritative context AND the
verifier's authoritative context — same passages on both sides.
"""
from __future__ import annotations

import time

from backend.agents.base import SpecialistOutput, ToolEvent
from backend.agents.synthesizer import synthesize

# Hardcoded KB stub — three passages. Each query gets all three; the
# synthesizer picks what's relevant. A real retriever would rank/filter.
_KB_PASSAGES: list[dict] = [
    {
        "passage": (
            "Return policy: most products may be returned within 90 days with the "
            "original receipt. Opened paint can be returned within 30 days for "
            "store credit only. Major appliances must be returned within 48 hours "
            "of delivery. Online orders can be returned in-store or by mail."
        ),
        "score": 0.91,
        "source": "return_policy.pdf",
    },
    {
        "passage": (
            "Cordless Drill X-200: 20V brushless motor, 2.0Ah lithium-ion battery, "
            "1/2-inch chuck, 3-year limited warranty covering defects in materials "
            "and workmanship. Battery and charger sold with the kit. LED work light. "
            "Compatible with all 20V Max system batteries."
        ),
        "score": 0.85,
        "source": "product_guide.pdf",
    },
    {
        "passage": (
            "Standard manufacturer warranty terms: power tools carry a 3-year limited "
            "warranty; outdoor power equipment carries 2 years; major appliances "
            "carry 1 year on parts and labor. Extended protection plans add 2-5 years "
            "and must be purchased within 30 days of the original sale. Consumables "
            "(blades, bits, batteries beyond 90 days) are not covered."
        ),
        "score": 0.71,
        "source": "warranty.pdf",
    },
]


def _retrieve(query: str) -> tuple[list[dict], int]:
    """Simulate a retrieval call. Returns (passages, latency_ms)."""
    t0 = time.perf_counter()
    # Pretend network/index work — in stub mode this is essentially zero.
    passages = list(_KB_PASSAGES)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    return passages, latency_ms


def _format_context(passages: list[dict]) -> str:
    lines = ["Knowledge base passages (authoritative):"]
    for i, p in enumerate(passages, start=1):
        lines.append(f"[{i}] source={p['source']} score={p['score']:.2f}")
        lines.append(f"    {p['passage']}")
    return "\n".join(lines)


def handle(*, utterance: str) -> SpecialistOutput:
    passages, retrieval_ms = _retrieve(utterance)

    tool_events = [
        ToolEvent(
            event_type="retrieval",
            latency_ms=retrieval_ms,
            metadata={
                "query": utterance,
                "k": len(passages),
                "passages": [
                    {
                        "passage_id":     f"kb:{p['source']}",
                        "source":         p["source"],
                        "content":        p["passage"],
                        "semantic_score": p["score"],
                        "keyword_score":  p["score"],
                        "fused_score":    p["score"],
                        "rerank_score":   p["score"],
                    }
                    for p in passages
                ],
                "retriever": "stub",
            },
        )
    ]

    context = _format_context(passages)
    synth = synthesize(utterance=utterance, context=context)

    return SpecialistOutput(
        response_text=synth.response_text,
        context=context,
        synthesis=synth,
        tool_events=tool_events,
    )

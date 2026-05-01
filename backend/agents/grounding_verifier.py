"""Quote-grounded LLM-as-judge verifier — the LexiScan technique.

LexiScan (legal AI) demonstrated that catching hallucinated citations
required a *separate* quote-checking pass: ask a second model to enumerate the
factual claims in the answer and verify each against the source documents. We
adapt that here for retail CX:

  1. Synthesizer drafts a response from retrieved context.
  2. Verifier (this module) inspects the response against the SAME context
     passages and decides whether each factual claim is supported.
  3. If any claim is ungrounded → orchestrator retries synthesis once with a
     stricter prompt; if still ungrounded → refuse.

This is intentionally a separate model call (Gemini Flash, cheaper than Pro):
the synthesizer's own self-assessment cannot be trusted — that's the whole
point of the verifier. The verifier MUST NOT be merged into the synthesizer
prompt or skipped "for now" (CLAUDE.md §5).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from backend.config import get_settings
from backend.llm.client import LLMResult, generate_json, load_prompt, render

log = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    grounded: bool
    score: float
    failed_claims: list[str] = field(default_factory=list)
    rationale: str = ""
    llm: LLMResult | None = None


def verify(
    *,
    response_text: str,
    context: str,
) -> VerificationResult:
    """Run the verifier. Verifier-side errors degrade safe — we treat any
    parse error as ungrounded (better to refuse than to ship a hallucination)."""
    settings = get_settings()
    template = load_prompt("grounding_verifier")
    prompt = render(
        template,
        CONTEXT=context or "(no context available)",
        RESPONSE=response_text,
    )

    parsed, llm = generate_json(
        # Flash is plenty for the LexiScan rubric — cheaper than Pro and
        # avoids the thinking-token overhead.
        model=settings.gemini_flash_model,
        prompt=prompt,
        temperature=0.0,
        max_output_tokens=1024,
    )

    grounded = bool(parsed.get("grounded", False))
    score = float(parsed.get("score", 0.0))
    failed_claims = [str(c) for c in parsed.get("failed_claims", []) or []]
    rationale = str(parsed.get("rationale", ""))

    # Belt-and-braces: even if the model says grounded=true, fail the verdict
    # if score < threshold. Conservative on purpose (CLAUDE.md §5).
    if score < settings.grounding_min_score:
        grounded = False

    return VerificationResult(
        grounded=grounded,
        score=score,
        failed_claims=failed_claims,
        rationale=rationale,
        llm=llm,
    )

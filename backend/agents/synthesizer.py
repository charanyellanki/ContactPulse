"""Response synthesizer (Gemini 2.0 Pro).

Composes a customer-facing response grounded in the supplied context. Returns
the raw text plus the list of factual claims it considers itself to have made
— the grounding verifier checks each one.

Claim extraction is sentence-level: simple heuristic that splits on `.!?`
and drops short / non-substantive sentences. Good enough for MVP; the
verifier ultimately re-derives claims from the response anyway.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from backend.config import get_settings
from backend.llm.client import LLMResult, generate, load_prompt, render

log = logging.getLogger(__name__)


@dataclass
class SynthesisResult:
    response_text: str
    claims: list[str] = field(default_factory=list)
    llm: LLMResult | None = None
    attempt: int = 1


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _extract_claims(text: str) -> list[str]:
    """Crude claim extraction. We treat every non-trivial sentence as a claim;
    the verifier will catch over-counts (pleasantries are excluded explicitly
    in the verifier's rubric)."""
    claims: list[str] = []
    for s in _SENTENCE_SPLIT.split(text.strip()):
        s = s.strip()
        if len(s) < 12:
            continue
        claims.append(s)
    return claims


def synthesize(
    *,
    utterance: str,
    context: str,
    stricter: bool = False,
) -> SynthesisResult:
    """Generate a response. `stricter=True` is used on the grounding retry —
    we inject an extra clause telling the model to refuse rather than guess."""
    settings = get_settings()
    template = load_prompt("synthesizer")
    strictness = (
        "STRICT MODE: A previous draft was rejected for ungrounded claims. "
        "If the context does not directly support an answer, REFUSE — say you "
        "do not have that information. Do not paraphrase weakly-supported facts."
        if stricter
        else ""
    )
    prompt = render(
        template,
        UTTERANCE=utterance,
        CONTEXT=context or "(no context available)",
        STRICTNESS=strictness,
    )

    llm = generate(
        model=settings.gemini_pro_model,
        prompt=prompt,
        temperature=0.2 if not stricter else 0.0,
        # 2.5-pro is a thinking model — it spends ~150-300 tokens internally
        # before emitting text. Budget covers thinking + a 3-sentence reply.
        max_output_tokens=1024,
    )
    text = llm.text.strip()
    return SynthesisResult(
        response_text=text,
        claims=_extract_claims(text),
        llm=llm,
        attempt=2 if stricter else 1,
    )

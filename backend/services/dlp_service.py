"""DLP / PII redaction service — stub.

Real implementation will call Google Cloud DLP to redact PII in user
utterances and STT transcripts at the boundary, before any payload reaches
storage or downstream agents (ARCHITECTURE.md §4.1, SPEC.md §5).
"""
from __future__ import annotations


class DlpService:
    """Stub. Real wiring lands in step 3 of the UI-first scaffold."""

    def redact(self, text: str) -> tuple[str, bool]:
        """Returns (redacted_text, was_redacted). No-op for the scaffold."""
        raise NotImplementedError("DLP wiring not implemented yet.")

"""Per-service circuit breaker for downstream calls.

CLAUDE.md §6 + ARCHITECTURE.md §11: every LLM/tool call is wrapped so a
chain of failures degrades gracefully instead of blowing up the API. We keep
this deliberately simple — module-level state, sliding-window failure counts.
A more sophisticated implementation (Hystrix-style half-open probes) is a
later concern.

State per `name` (e.g. "gemini_flash", "gemini_pro", "dlp"):
  - rolling list of failure timestamps
  - if `>= threshold` failures occur in `window_seconds`, the circuit is OPEN
  - while OPEN, calls raise CircuitOpenError immediately
  - failures auto-age out — no separate "reset" timer
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque

from backend.config import get_settings


class CircuitOpenError(RuntimeError):
    """Raised when a service is currently shed-loaded by the breaker."""


_lock = threading.Lock()
_failures: dict[str, Deque[float]] = defaultdict(deque)


def _settings_thresholds() -> tuple[int, int]:
    s = get_settings()
    return s.circuit_breaker_failure_threshold, s.circuit_breaker_window_seconds


def _prune(name: str, now: float, window: int) -> None:
    q = _failures[name]
    while q and (now - q[0]) > window:
        q.popleft()


def check(name: str) -> None:
    """Raise CircuitOpenError if the circuit for `name` is currently open."""
    threshold, window = _settings_thresholds()
    now = time.monotonic()
    with _lock:
        _prune(name, now, window)
        if len(_failures[name]) >= threshold:
            raise CircuitOpenError(
                f"circuit open for {name}: "
                f"{len(_failures[name])} failures in the last {window}s"
            )


def record_failure(name: str) -> None:
    """Record one failure for `name`. Caller decides what counts as a failure."""
    _, window = _settings_thresholds()
    now = time.monotonic()
    with _lock:
        _prune(name, now, window)
        _failures[name].append(now)


def record_success(name: str) -> None:
    """Clear the failure history for `name` after a successful call."""
    with _lock:
        _failures[name].clear()


def reset_all() -> None:
    """Test-only — wipe all circuit state."""
    with _lock:
        _failures.clear()

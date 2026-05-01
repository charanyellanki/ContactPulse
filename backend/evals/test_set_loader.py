"""Load `test_set.jsonl` from disk.

Tiny module so the runner and error-analysis scripts can share one
canonical loader without circular imports.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DEFAULT_PATH = Path(__file__).resolve().parent / "test_set.jsonl"


def load(path: Path | None = None) -> list[dict[str, Any]]:
    """Read the JSONL test set into a list of dicts. Raises if missing."""
    p = path or _DEFAULT_PATH
    if not p.exists():
        raise FileNotFoundError(
            f"test set not found at {p}. Run `python -m backend.evals.build_test_set` first."
        )
    rows: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows

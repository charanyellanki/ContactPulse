"""Cluster failed queries from a run and save the analysis.

Inputs: a `results.jsonl` file (local path OR `gs://contactpulse-evals/runs/<run_id>/results.jsonl`).
Outputs: a printed cluster summary + `error_analysis.json` written next to the
input.

Failure clusters (in priority order — first matching cluster wins):
  - wrong_intent       — intent_correct == False
  - retrieval_miss     — hit == False (only product_qa)
  - hallucination      — hallucinated == "yes"
  - refused_correctly  — expected_outcome == Refused AND derived_outcome == "refused"
  - refused_incorrectly — expected_outcome != Refused AND derived_outcome == "refused"
  - incomplete         — task_success == "partial"
  - other              — fallthrough

Failures are: task_success in {"failed", "partial"} OR outcome_correct == False
OR hallucinated == "yes" OR (expected_outcome != Refused AND derived_outcome == refused).

Usage:
    python -m backend.evals.error_analysis                              # latest run from GCS
    python -m backend.evals.error_analysis --run-id evr_20260501_123456 # specific run
    python -m backend.evals.error_analysis --local /tmp/results.jsonl   # local file
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.config import get_settings

log = logging.getLogger("error_analysis")


CLUSTER_ORDER: list[str] = [
    "wrong_intent",
    "retrieval_miss",
    "hallucination",
    "refused_correctly",
    "refused_incorrectly",
    "incomplete",
    "other",
]


@dataclass
class Cluster:
    name: str
    examples: list[dict[str, Any]] = field(default_factory=list)


def _is_failure(row: dict[str, Any]) -> bool:
    """Whether a per-query row should be considered a failure for analysis."""
    if row.get("task_success") in {"failed", "error", "partial"}:
        return True
    if row.get("hallucinated") == "yes":
        return True
    if not row.get("outcome_correct", True):
        return True
    if not row.get("intent_correct", True):
        return True
    return False


def _classify(row: dict[str, Any]) -> str:
    """Bucket a failed row into a cluster. First match wins."""
    expected = (row.get("expected_outcome") or "").strip().lower()
    derived = (row.get("derived_outcome") or "").strip().lower()

    if not row.get("intent_correct", True):
        return "wrong_intent"
    if row.get("journey") == "product_qa" and not row.get("hit", True):
        return "retrieval_miss"
    if row.get("hallucinated") == "yes":
        return "hallucination"
    if expected == "refused" and derived == "refused":
        return "refused_correctly"
    if expected != "refused" and derived == "refused":
        return "refused_incorrectly"
    if row.get("task_success") == "partial":
        return "incomplete"
    return "other"


def _read_local(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _read_gcs(uri: str) -> list[dict[str, Any]]:
    from google.cloud import storage

    assert uri.startswith("gs://")
    rest = uri[len("gs://"):]
    bucket_name, _, blob_name = rest.partition("/")

    settings = get_settings()
    client = storage.Client(project=settings.project_id)
    bucket = client.get_bucket(bucket_name)
    blob = bucket.blob(blob_name)
    text = blob.download_as_text()
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _latest_run_id() -> str:
    """Find the most recent run by listing run_id prefixes in the evals bucket."""
    from google.cloud import storage

    settings = get_settings()
    client = storage.Client(project=settings.project_id)
    bucket = client.bucket(settings.gcs_evals_bucket)
    # List blobs under "runs/" — pick the alphabetically-greatest prefix
    # (run_ids are timestamp-prefixed, so lexicographic == chronological).
    prefixes: set[str] = set()
    for blob in client.list_blobs(bucket, prefix="runs/"):
        # blob.name like runs/<run_id>/results.jsonl
        parts = blob.name.split("/")
        if len(parts) >= 2 and parts[1]:
            prefixes.add(parts[1])
    if not prefixes:
        raise RuntimeError(f"no runs found in gs://{settings.gcs_evals_bucket}/runs/")
    return sorted(prefixes)[-1]


def analyze(rows: list[dict[str, Any]]) -> tuple[OrderedDict[str, Cluster], int]:
    """Cluster failures. Returns (clusters_by_name, total_failures)."""
    clusters: OrderedDict[str, Cluster] = OrderedDict(
        (name, Cluster(name=name)) for name in CLUSTER_ORDER
    )

    failures = [r for r in rows if _is_failure(r)]
    for row in failures:
        cluster_name = _classify(row)
        clusters[cluster_name].examples.append(row)
    return clusters, len(failures)


def print_summary(
    clusters: OrderedDict[str, Cluster], total_failures: int, total_rows: int
) -> None:
    print()
    print("=" * 70)
    print(f"  Error analysis — {total_failures} failures of {total_rows} queries")
    print("=" * 70)
    for name, cluster in clusters.items():
        n = len(cluster.examples)
        if n == 0:
            continue
        pct_of_failures = (n / total_failures * 100) if total_failures else 0
        print(f"\n  {name}: {n} cases ({pct_of_failures:.0f}% of failures)")
        for ex in cluster.examples[:2]:
            print(f"    [{ex.get('query_id')}] {ex.get('utterance')[:80]}")
            response_text = (ex.get('response_text') or '').replace('\n', ' ')[:120]
            print(f"        → {response_text}")
    print()


def write_summary(
    *,
    run_id: str | None,
    clusters: OrderedDict[str, Cluster],
    total_failures: int,
    total_rows: int,
    output_local: Path | None,
) -> str:
    """Write cluster summary to GCS (and optionally a local copy)."""
    summary = {
        "run_id": run_id,
        "total_rows": total_rows,
        "total_failures": total_failures,
        "clusters": [
            {
                "name": cluster.name,
                "count": len(cluster.examples),
                "examples": [
                    {
                        "query_id":      ex.get("query_id"),
                        "utterance":     ex.get("utterance"),
                        "response_text": ex.get("response_text"),
                        "expected_outcome": ex.get("expected_outcome"),
                        "derived_outcome":  ex.get("derived_outcome"),
                        "task_success":  ex.get("task_success"),
                        "hallucinated":  ex.get("hallucinated"),
                        "intent_correct": ex.get("intent_correct"),
                    }
                    for ex in cluster.examples[:5]
                ],
            }
            for cluster in clusters.values()
            if cluster.examples
        ],
    }
    text = json.dumps(summary, indent=2)

    if output_local is not None:
        output_local.write_text(text)

    if run_id is None:
        return ""

    try:
        from google.cloud import storage
        settings = get_settings()
        client = storage.Client(project=settings.project_id)
        bucket = client.bucket(settings.gcs_evals_bucket)
        blob = bucket.blob(f"runs/{run_id}/error_analysis.json")
        blob.upload_from_string(text, content_type="application/json")
        return f"gs://{settings.gcs_evals_bucket}/runs/{run_id}/error_analysis.json"
    except Exception as exc:  # noqa: BLE001
        log.warning("GCS write failed: %s", exc)
        return ""


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("google").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=None, help="run_id to analyze (defaults to latest)")
    parser.add_argument("--local", type=Path, default=None, help="local results.jsonl to analyze")
    parser.add_argument(
        "--out-local", type=Path, default=None, help="also write error_analysis.json locally"
    )
    args = parser.parse_args()

    run_id: str | None = None
    if args.local is not None:
        rows = _read_local(args.local)
    else:
        run_id = args.run_id or _latest_run_id()
        settings = get_settings()
        uri = f"gs://{settings.gcs_evals_bucket}/runs/{run_id}/results.jsonl"
        log.info("reading %s", uri)
        rows = _read_gcs(uri)

    clusters, total_failures = analyze(rows)
    print_summary(clusters, total_failures, total_rows=len(rows))

    uri = write_summary(
        run_id=run_id,
        clusters=clusters,
        total_failures=total_failures,
        total_rows=len(rows),
        output_local=args.out_local,
    )
    if uri:
        print(f"  wrote cluster summary: {uri}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Seed the ContactPulse BigQuery dataset with synthetic data.

Idempotent: ensures the dataset exists, applies DDL from
`backend/infra/bigquery_schemas.sql`, truncates the four target tables, then
inserts a deterministic synthetic dataset.

Usage:
    poetry run python -m backend.scripts.seed_bigquery
    # or, with the project venv activated:
    python -m backend.scripts.seed_bigquery

Auth: Application Default Credentials. Run once before this script:
    gcloud auth application-default login
    gcloud config set project contactpulse-dev

The customer IDs match the mock customers already shipped in the frontend
fixture set — `1042`, `2087`, `3391`, `4156`, `5203`, `6078`. Conversations
randomly draw from these (or anonymous for refused/escalated outcomes); the
distributions, journey/outcome shares, and per-stage latency ranges are the
ones called out in the seed task.

Determinism: a fixed RNG seed (`SEED_RNG_SEED`) means the same dataset is
produced on every run. Bump the seed if you want a fresh shuffle.
"""
from __future__ import annotations

import json
import logging
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.cloud import bigquery
from google.cloud.exceptions import NotFound

from backend.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("seed_bigquery")

SEED_RNG_SEED = 20260501

# Deterministic anchor — the script generates `created_at` timestamps in the
# 7 days *up to* this anchor (UTC). Using a fixed anchor instead of `now()`
# keeps the seed dataset reproducible; shift it when you want fresher data.
NOW_ANCHOR = datetime(2026, 5, 1, 18, 0, 0, tzinfo=timezone.utc)

CUSTOMER_IDS = ["1042", "2087", "3391", "4156", "5203", "6078"]

# Frontend fixture parity — these are the labels/tiers already used in
# `backend/fixtures/customers.json`. Repos derive `display_label` from
# customer_id+tier at read time, so only the tier needs to be persisted.
CUSTOMER_PROFILES: dict[str, dict[str, object]] = {
    "1042": {"tier": "gold",   "lifetime_value": 12450.0, "open_orders": 3, "recent_journey": "order_status"},
    "2087": {"tier": "silver", "lifetime_value":  4280.0, "open_orders": 0, "recent_journey": "product_qa"},
    "3391": {"tier": "bronze", "lifetime_value":   612.0, "open_orders": 1, "recent_journey": "product_qa"},
    "4156": {"tier": "gold",   "lifetime_value": 18920.0, "open_orders": 2, "recent_journey": "service_request"},
    "5203": {"tier": "silver", "lifetime_value":  3105.0, "open_orders": 0, "recent_journey": "product_qa"},
    "6078": {"tier": "bronze", "lifetime_value":   248.0, "open_orders": 0, "recent_journey": None},
}

# Conversation-level distributions
N_CONVERSATIONS = 50
JOURNEY_WEIGHTS = [("order_status", 0.40), ("product_qa", 0.35), ("service_request", 0.25)]
MODALITY_WEIGHTS = [("voice", 0.60), ("chat", 0.40)]
OUTCOME_WEIGHTS = [("contained", 0.55), ("escalated", 0.30), ("refused", 0.15)]

# Per-stage latency ranges (ms) — task spec
STAGE_LATENCY_MS: dict[str, tuple[int, int]] = {
    "stt":                    (200, 400),
    "intent_routing":         (100, 200),
    "retrieval":              (300, 600),
    "synthesis":              (400, 800),
    "grounding_verification": (150, 300),
    "tts":                    (200, 400),
}

# Order matters — events are written with monotonically increasing timestamps.
# 8 events per conversation = 50 * 8 = 400 trace rows.
EVENT_ORDER: list[str] = [
    "user_message",
    "stt",
    "intent_routing",
    "retrieval",
    "synthesis",
    "grounding_verification",
    "tts",
    "agent_response",
]


# ─── Synthesis / sample text per journey ──────────────────────────────────

JOURNEY_USER_INPUTS: dict[str, list[str]] = {
    "order_status": [
        "Where's my order #4521? It was supposed to arrive Friday.",
        "Can you check the status of my recent order? I think it's order 7812.",
        "I need to change the delivery address on my order 9034.",
        "My order says delivered but I haven't received it.",
        "When will order #6677 arrive?",
    ],
    "product_qa": [
        "Does the cordless drill X-200 come with a warranty?",
        "What's your return policy on opened paint?",
        "Is the LED floodlight FL-90 dimmable?",
        "Can the smart thermostat T-300 work without a C-wire?",
        "Are the patio chairs PC-12 weather resistant?",
    ],
    "service_request": [
        "I'd like to schedule an installation for a water heater.",
        "Can someone come out next week to look at my HVAC?",
        "I need to book a consultation for kitchen cabinets.",
        "Schedule a repair visit for my dishwasher please.",
        "I want to set up a service appointment for ceiling fan install.",
    ],
}

JOURNEY_AGENT_RESPONSES: dict[str, list[str]] = {
    "order_status": [
        "Order #4521 (1× Cordless Drill X-200) shipped April 28 and is out for delivery today, ETA 2-6 PM local.",
        "Order #7812 was delivered on April 29 at 2:14 PM. Carrier scan confirms drop-off at the front door.",
        "I can update the delivery address on order #9034 since it hasn't shipped yet. Could you confirm the new address?",
        "I see the carrier marked it delivered. I'll open a missing-package case and email you a confirmation.",
        "Order #6677 is in transit, currently in Atlanta. ETA is May 3 between 9 AM and 1 PM.",
    ],
    "product_qa": [
        "The Cordless Drill X-200 carries a 3-year limited warranty covering defects in materials and workmanship.",
        "Opened paint can be returned within 30 days with the receipt for store credit only.",
        "Yes, the LED floodlight FL-90 is fully dimmable when paired with a compatible 0-10V dimmer.",
        "The Smart Thermostat T-300 supports C-wire-free operation when used with the included power adapter.",
        "Patio chairs PC-12 are rated for outdoor use and treated for UV and moisture resistance.",
    ],
    "service_request": [
        "I can book a water heater install. Earliest available is Tuesday 9-12 — does that work?",
        "I have HVAC technicians available next Wed and Thu. Which window suits you, 8-12 or 1-5?",
        "Kitchen cabinet consultations are available Mon and Fri. Would you prefer in-store or in-home?",
        "I can schedule a dishwasher repair visit. The next opening is Thursday 10-2.",
        "Ceiling fan install is available Saturday morning 8-12. Confirm to book.",
    ],
}

REFUSAL_TEXT = (
    "I don't have a verified answer for that in our knowledge base. "
    "Let me connect you with a specialist who can help."
)
ESCALATION_TEXT = (
    "I'd like to make sure this is handled correctly — connecting you with a "
    "human associate now."
)

JOURNEY_CITATIONS: dict[str, str] = {
    "order_status":    "order_record",
    "product_qa":      "kb_passage",
    "service_request": "scheduling_slot",
}


# ─── Helpers ──────────────────────────────────────────────────────────────


def _weighted_choice(rng: random.Random, weighted: list[tuple[str, float]]) -> str:
    items, weights = zip(*weighted, strict=True)
    return rng.choices(items, weights=weights, k=1)[0]


def _ts_iso(ts: datetime) -> str:
    """RFC 3339 / ISO 8601 with millisecond precision and trailing `Z` —
    matches the format already used in the JSON fixtures shipped with the
    frontend so trace rendering looks identical regardless of source."""
    utc = ts.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"


def _read_ddl(project_id: str, dataset: str) -> list[str]:
    """Load DDL from disk and substitute identifiers; split into statements."""
    ddl_path = Path(__file__).resolve().parent.parent / "infra" / "bigquery_schemas.sql"
    raw = ddl_path.read_text()
    rendered = raw.replace("${PROJECT_ID}", project_id).replace("${BQ_DATASET}", dataset)
    # Strip line comments, then split on `;` for statement-by-statement exec.
    lines = [ln for ln in rendered.splitlines() if not ln.strip().startswith("--")]
    body = "\n".join(lines)
    return [s.strip() for s in body.split(";") if s.strip()]


def _ensure_dataset(client: bigquery.Client, dataset_id: str, location: str = "US") -> None:
    ref = bigquery.Dataset(f"{client.project}.{dataset_id}")
    try:
        client.get_dataset(ref)
        log.info("dataset %s already exists", dataset_id)
    except NotFound:
        ref.location = location
        client.create_dataset(ref)
        log.info("created dataset %s in %s", dataset_id, location)


def _apply_ddl(client: bigquery.Client, project_id: str, dataset: str) -> None:
    for stmt in _read_ddl(project_id, dataset):
        log.info("applying DDL: %s ...", stmt.splitlines()[0])
        client.query(stmt).result()


def _truncate(client: bigquery.Client, project_id: str, dataset: str, tables: list[str]) -> None:
    for t in tables:
        client.query(f"TRUNCATE TABLE `{project_id}.{dataset}.{t}`").result()
        log.info("truncated %s", t)


# ─── Generators ───────────────────────────────────────────────────────────


def _gen_customers() -> list[dict]:
    return [
        {
            "customer_id":    cid,
            "tier":           p["tier"],
            "lifetime_value": p["lifetime_value"],
            "open_orders":    p["open_orders"],
            "recent_journey": p["recent_journey"],
        }
        for cid, p in CUSTOMER_PROFILES.items()
    ]


# Realistic-looking SKUs per customer for the OrderStatusAgent. Three orders
# per customer, deliberately spanning delivered / in_transit / processing so
# the agent has interesting status text to surface.
ORDER_SKUS: list[tuple[str, str]] = [
    ("HD-DRL-X200", "Cordless Drill X-200"),
    ("HD-FLT-FL90", "LED Floodlight FL-90"),
    ("HD-THR-T300", "Smart Thermostat T-300"),
    ("HD-CHR-PC12", "Patio Chair PC-12"),
    ("HD-PNT-BSE5", "Premium Interior Paint, 5gal"),
    ("HD-FAN-CF24", "Ceiling Fan CF-24"),
    ("HD-WTR-WH40", "Tankless Water Heater WH-40"),
    ("HD-DSH-DW18", "Stainless Dishwasher DW-18"),
    ("HD-LAW-LM55", "Cordless Lawn Mower LM-55"),
]

ORDER_STATUSES: list[str] = ["delivered", "in_transit", "processing"]


def _gen_orders(rng: random.Random) -> list[dict]:
    """Three orders per seeded customer — one per status. Deterministic via
    the shared RNG. Order dates fan out from the seed anchor so the agent's
    ORDER BY order_date DESC LIMIT 3 query returns the most recent first."""
    rows: list[dict] = []
    order_seq = 1000
    for customer_id in CUSTOMER_IDS:
        # Walk back from anchor: most recent order is "processing", oldest "delivered"
        for offset_days, status in (
            (1, "processing"),
            (4, "in_transit"),
            (12, "delivered"),
        ):
            sku, product_name = rng.choice(ORDER_SKUS)
            order_date = NOW_ANCHOR - timedelta(days=offset_days, hours=rng.randint(0, 23))
            eta: datetime | None
            tracking: str | None
            if status == "delivered":
                eta = order_date + timedelta(days=rng.randint(2, 5))
                tracking = f"1Z{rng.randint(10**8, 10**9 - 1)}"
            elif status == "in_transit":
                eta = NOW_ANCHOR + timedelta(days=rng.randint(1, 3))
                tracking = f"1Z{rng.randint(10**8, 10**9 - 1)}"
            else:  # processing
                eta = NOW_ANCHOR + timedelta(days=rng.randint(4, 7))
                tracking = None
            rows.append(
                {
                    "order_id":     f"#{order_seq}",
                    "customer_id":  customer_id,
                    "sku":          sku,
                    "product_name": product_name,
                    "quantity":     rng.randint(1, 3),
                    "status":       status,
                    "order_date":   _ts_iso(order_date),
                    "eta":          _ts_iso(eta) if eta else None,
                    "tracking_no":  tracking,
                }
            )
            order_seq += 1
    return rows


def _gen_conversations(rng: random.Random) -> list[dict]:
    """Return list of conversation dicts. Order matters: callers pair index 0
    with the first 8 trace events."""
    rows: list[dict] = []
    # Spread `created_at` evenly across the past 7 days, ascending
    span = timedelta(days=7)
    start = NOW_ANCHOR - span
    for i in range(N_CONVERSATIONS):
        # Even-ish distribution with jitter
        frac = (i + 0.5) / N_CONVERSATIONS
        jitter_s = rng.randint(-1800, 1800)
        created_at = start + frac * span + timedelta(seconds=jitter_s)

        modality = _weighted_choice(rng, MODALITY_WEIGHTS)
        journey = _weighted_choice(rng, JOURNEY_WEIGHTS)
        outcome = _weighted_choice(rng, OUTCOME_WEIGHTS)

        # Anonymous on a slim subset of escalations / refusals
        anonymous = outcome != "contained" and rng.random() < 0.30
        customer_id: str | None = None
        tier: str | None = None
        if not anonymous:
            customer_id = rng.choice(CUSTOMER_IDS)
            tier = CUSTOMER_PROFILES[customer_id]["tier"]  # type: ignore[assignment]

        # Total turn latency: 800-3500ms, with realistic variance per outcome
        base_latency = rng.randint(800, 3500)
        if outcome == "escalated":
            base_latency = int(base_latency * rng.uniform(1.05, 1.4))
        latency_p50_ms = min(base_latency, 4500)

        cost_usd = round(rng.uniform(0.0010, 0.0018), 6)
        turns = 1 if outcome != "escalated" else rng.choice([1, 2, 2, 3])

        trace_id = f"trc_{i+1:03d}_{journey[:3]}_{outcome[:3]}"

        rows.append(
            {
                "trace_id":       trace_id,
                "modality":       modality,
                "customer_id":    customer_id,
                "tier":           tier,
                "journey":        journey,
                "outcome":        outcome,
                "turns":          turns,
                "latency_p50_ms": latency_p50_ms,
                "cost_usd":       cost_usd,
                "created_at":     _ts_iso(created_at),
            }
        )
    return rows


def _gen_trace_events(rng: random.Random, conv: dict) -> list[dict]:
    trace_id = conv["trace_id"]
    journey = conv["journey"]
    modality = conv["modality"]
    outcome = conv["outcome"]
    started_at = datetime.fromisoformat(conv["created_at"])

    user_input = rng.choice(JOURNEY_USER_INPUTS[journey])
    response_text = (
        REFUSAL_TEXT      if outcome == "refused"   else
        ESCALATION_TEXT   if outcome == "escalated" else
        rng.choice(JOURNEY_AGENT_RESPONSES[journey])
    )

    # Stage latencies — sampled per call, used both for `timestamp` advancement
    # and for `latency_ms` on the corresponding rows.
    stage_lat = {
        s: rng.randint(lo, hi) for s, (lo, hi) in STAGE_LATENCY_MS.items()
    }

    # Confidence / verifier dynamics keyed off outcome
    if outcome == "contained":
        router_confidence = round(rng.uniform(0.82, 0.97), 3)
        verifier_score    = round(rng.uniform(0.84, 0.97), 3)
        verifier_verdict  = "pass"
    elif outcome == "refused":
        router_confidence = round(rng.uniform(0.72, 0.88), 3)
        verifier_score    = round(rng.uniform(0.40, 0.65), 3)
        verifier_verdict  = "fail"
    else:  # escalated
        router_confidence = round(rng.uniform(0.42, 0.68), 3)
        verifier_score    = round(rng.uniform(0.55, 0.78), 3)
        verifier_verdict  = "fail" if rng.random() < 0.4 else "pass"

    intent = "ambiguous" if outcome == "escalated" and router_confidence < 0.55 else journey

    citation_id = f"{JOURNEY_CITATIONS[journey]}:{rng.randint(1000, 9999)}"

    events: list[dict] = []
    cursor = started_at

    for et in EVENT_ORDER:
        # voice gets stt+tts; chat skips them but we still emit the rows for
        # consistent shape (see CLAUDE.md §2 — chat bypasses STT/TTS).
        skipped = (et == "stt" and modality != "voice") or (et == "tts" and modality != "voice")
        if et in STAGE_LATENCY_MS:
            latency_ms = 0 if skipped else stage_lat[et]
        else:
            latency_ms = 0  # bookend rows (user_message, agent_response)

        # Advance cursor by half this stage's latency before stamping (gives
        # plausibly-spaced timestamps without claiming start==end).
        cursor = cursor + timedelta(milliseconds=max(latency_ms, 1))

        input_text: str | None = None
        output_text: str | None = None
        metadata: dict = {}
        pii_redacted = False

        if et == "user_message":
            input_text = user_input
            metadata = {"channel": modality}
            pii_redacted = True
        elif et == "stt":
            if skipped:
                metadata = {"skipped": True, "reason": "modality=chat"}
            else:
                output_text = user_input
                metadata = {
                    "audio_duration_ms": stage_lat["stt"] * rng.randint(8, 14),
                    "confidence":        round(rng.uniform(0.86, 0.98), 3),
                    "model":             "google-stt-default",
                }
            pii_redacted = True
        elif et == "intent_routing":
            metadata = {
                "model":      "gemini-2.0-flash",
                "intent":     intent,
                "confidence": router_confidence,
                "threshold":  0.7,
                "reasoning":  f"User phrasing aligns with {journey} signals.",
                "candidates": [
                    {"intent": journey,           "score": router_confidence},
                    {"intent": "out_of_scope",    "score": round(1 - router_confidence, 3)},
                ],
            }
        elif et == "retrieval":
            metadata = {
                "query": user_input[:120],
                "k":     5,
                "passages": [
                    {
                        "passage_id":     citation_id,
                        "source":         JOURNEY_CITATIONS[journey],
                        "content":        f"{journey} reference passage for {citation_id}",
                        "semantic_score": round(rng.uniform(0.62, 0.91), 3),
                        "keyword_score":  round(rng.uniform(0.40, 0.85), 3),
                        "fused_score":    round(rng.uniform(0.55, 0.92), 3),
                        "rerank_score":   round(rng.uniform(0.60, 0.95), 3),
                    }
                ],
            }
        elif et == "synthesis":
            output_text = response_text
            metadata = {
                "model":   "gemini-2.0-pro",
                "attempt": 1,
                "citations": [
                    {"passage_id": citation_id, "span": f"reference span for {citation_id}"}
                ],
            }
        elif et == "grounding_verification":
            metadata = {
                "model":             "gemini-2.0-pro",
                "attempt":           1,
                "verdict":           verifier_verdict,
                "score":             verifier_score,
                "threshold":         0.8,
                "rationale":         (
                    "All factual claims supported by the cited passage."
                    if verifier_verdict == "pass"
                    else "One or more claims could not be grounded against retrieved evidence."
                ),
                "ungrounded_claims": (
                    [] if verifier_verdict == "pass"
                    else [{"claim": "specific spec referenced",
                           "reason": "not present in retrieved passage"}]
                ),
            }
        elif et == "tts":
            if skipped:
                metadata = {"skipped": True, "reason": "modality=chat"}
            else:
                metadata = {
                    "voice":             "en-US-Neural2-F",
                    "audio_duration_ms": stage_lat["tts"] * rng.randint(8, 14),
                    "audio_url":         f"gs://contactpulse-audio/{trace_id}.mp3",
                }
        elif et == "agent_response":
            output_text = response_text
            metadata = {"channel": modality}

        events.append(
            {
                "event_id":     str(uuid.uuid4()),
                "trace_id":     trace_id,
                "event_type":   et,
                "input_text":   input_text,
                "output_text":  output_text,
                "metadata":     json.dumps(metadata),
                "latency_ms":   latency_ms,
                "pii_redacted": pii_redacted,
                "timestamp":    _ts_iso(cursor),
            }
        )

    return events


def _gen_eval_runs() -> list[dict]:
    """Three SYNTHETIC seed rows so the Operator Console's Eval Runs view has
    something to render before the first real eval has been executed.

    Every field that would identify a "real" run is deliberately tagged so a
    reader cannot mistake these for measured numbers:
      - run_id is `evr_seed_<n>` (no `_run_`)
      - git_sha is the literal string `seed-synthetic`
      - the values are placeholders that loosely walk toward the SPEC §8 targets

    The first real eval run (`python -m backend.evals.eval_runner`) writes a
    proper `evr_<timestamp>_<uuid>` row with the actual git SHA and measured
    metrics, which is what the README links to ("see contactpulse.eval_runs
    for the latest run").
    """
    def _at(days_ago: int) -> str:
        return _ts_iso(NOW_ANCHOR - timedelta(days=days_ago))

    return [
        {
            "run_id":                       "evr_seed_1",
            "git_sha":                      "seed-synthetic",
            "created_at":                   _at(7),
            "containment_rate":             0.71,
            "refusal_precision":            0.88,
            "task_success_order_status":    0.84,
            "task_success_product_qa":      0.69,
            "task_success_service_request": 0.47,
            "intent_accuracy":              0.83,
            "retrieval_hit_rate":           0.78,
            "hallucination_rate":           0.062,
            "latency_p50_ms":               1320,
            "latency_p95_ms":               1980,
            "cost_per_call_usd":            0.00148,
        },
        {
            "run_id":                       "evr_seed_2",
            "git_sha":                      "seed-synthetic",
            "created_at":                   _at(3),
            "containment_rate":             0.76,
            "refusal_precision":            0.91,
            "task_success_order_status":    0.87,
            "task_success_product_qa":      0.72,
            "task_success_service_request": 0.49,
            "intent_accuracy":              0.86,
            "retrieval_hit_rate":           0.81,
            "hallucination_rate":           0.048,
            "latency_p50_ms":               1265,
            "latency_p95_ms":               1880,
            "cost_per_call_usd":            0.00142,
        },
        {
            "run_id":                       "evr_seed_3",
            "git_sha":                      "seed-synthetic",
            "created_at":                   _at(0),
            "containment_rate":             0.82,
            "refusal_precision":            0.94,
            "task_success_order_status":    0.89,
            "task_success_product_qa":      0.74,
            "task_success_service_request": 0.51,
            "intent_accuracy":              0.88,
            "retrieval_hit_rate":           0.84,
            "hallucination_rate":           0.034,
            "latency_p50_ms":               1210,
            "latency_p95_ms":               1740,
            "cost_per_call_usd":            0.00138,
        },
    ]


# ─── Insert helpers ───────────────────────────────────────────────────────


def _insert(client: bigquery.Client, table_fqn: str, rows: list[dict]) -> None:
    """Use a load job from in-memory JSON — `insert_rows_json` would also
    work, but load jobs play nicer with TRUNCATE+INSERT idempotency and
    avoid streaming-buffer quirks."""
    if not rows:
        return
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        autodetect=False,
    )
    ndjson = "\n".join(json.dumps(r) for r in rows).encode("utf-8")
    from io import BytesIO
    job = client.load_table_from_file(
        BytesIO(ndjson),
        table_fqn,
        job_config=job_config,
    )
    job.result()


def _row_count(client: bigquery.Client, table_fqn: str) -> int:
    q = f"SELECT COUNT(*) AS c FROM {table_fqn}"
    return next(iter(client.query(q).result())).c  # type: ignore[no-any-return]


# ─── Entrypoint ───────────────────────────────────────────────────────────


def main() -> int:
    settings = get_settings()
    project_id = settings.project_id
    dataset = settings.bq_dataset

    log.info("seeding project=%s dataset=%s", project_id, dataset)

    client = bigquery.Client(project=project_id)

    _ensure_dataset(client, dataset)
    _apply_ddl(client, project_id, dataset)
    _truncate(
        client,
        project_id,
        dataset,
        ["conversations", "conversation_traces", "customers_context", "orders", "eval_runs"],
    )

    rng = random.Random(SEED_RNG_SEED)

    customers = _gen_customers()
    orders = _gen_orders(rng)
    conversations = _gen_conversations(rng)
    trace_events: list[dict] = []
    for conv in conversations:
        trace_events.extend(_gen_trace_events(rng, conv))
    eval_runs = _gen_eval_runs()

    fq = lambda t: f"{project_id}.{dataset}.{t}"  # noqa: E731 -- short-lived helper
    _insert(client, fq("customers_context"),    customers)
    _insert(client, fq("orders"),               orders)
    _insert(client, fq("conversations"),        conversations)
    _insert(client, fq("conversation_traces"),  trace_events)
    _insert(client, fq("eval_runs"),            eval_runs)

    log.info("row counts:")
    for t in ("customers_context", "orders", "conversations", "conversation_traces", "eval_runs"):
        n = _row_count(client, f"`{fq(t)}`")
        log.info("  %-22s %d", t, n)

    return 0


if __name__ == "__main__":
    sys.exit(main())

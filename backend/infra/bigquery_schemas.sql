-- ContactPulse BigQuery schema (MVP).
--
-- The dataset is created out-of-band (see backend/scripts/seed_bigquery.py
-- which `CREATE SCHEMA IF NOT EXISTS`'s it before exec'ing this file). All
-- statements are CREATE TABLE IF NOT EXISTS so applying the file is idempotent.
--
-- Placeholders `${PROJECT_ID}` and `${BQ_DATASET}` are substituted by the
-- seed script using simple string replacement (NOT BigQuery scripting params,
-- which can't be used in DDL identifiers).

CREATE TABLE IF NOT EXISTS `${PROJECT_ID}.${BQ_DATASET}.conversations` (
  trace_id        STRING    NOT NULL,
  modality        STRING    NOT NULL,
  customer_id     STRING,
  tier            STRING,
  journey         STRING    NOT NULL,
  outcome         STRING    NOT NULL,
  turns           INT64     NOT NULL,
  latency_p50_ms  INT64     NOT NULL,
  cost_usd        FLOAT64   NOT NULL,
  created_at      TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS `${PROJECT_ID}.${BQ_DATASET}.conversation_traces` (
  event_id     STRING    NOT NULL,
  trace_id     STRING    NOT NULL,
  event_type   STRING    NOT NULL,
  input_text   STRING,
  output_text  STRING,
  metadata     JSON,
  latency_ms   INT64     NOT NULL,
  pii_redacted BOOL      NOT NULL,
  timestamp    TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS `${PROJECT_ID}.${BQ_DATASET}.customers_context` (
  customer_id     STRING  NOT NULL,
  tier            STRING  NOT NULL,
  lifetime_value  FLOAT64 NOT NULL,
  open_orders     INT64   NOT NULL,
  recent_journey  STRING
);

CREATE TABLE IF NOT EXISTS `${PROJECT_ID}.${BQ_DATASET}.orders` (
  order_id     STRING    NOT NULL,
  customer_id  STRING    NOT NULL,
  sku          STRING    NOT NULL,
  product_name STRING    NOT NULL,
  quantity     INT64     NOT NULL,
  status       STRING    NOT NULL,
  order_date   TIMESTAMP NOT NULL,
  eta          TIMESTAMP,
  tracking_no  STRING
);

CREATE TABLE IF NOT EXISTS `${PROJECT_ID}.${BQ_DATASET}.eval_runs` (
  run_id                       STRING    NOT NULL,
  git_sha                      STRING    NOT NULL,
  created_at                   TIMESTAMP NOT NULL,
  -- Eval source classifier — 'golden' = labeled test set (intent/retrieval/
  -- refusal-precision available); 'production' = sampled from live
  -- conversations (no ground truth, label-dependent metrics are NULL).
  source                       STRING,
  sample_size                  INT64,
  sample_modality              STRING,
  -- Label-dependent metrics: NULL on production rows by design.
  refusal_precision            FLOAT64,
  intent_accuracy              FLOAT64,
  retrieval_hit_rate           FLOAT64,
  -- Telemetry-derived metrics: populated for both sources.
  containment_rate             FLOAT64   NOT NULL,
  task_success_order_status    FLOAT64,
  task_success_product_qa      FLOAT64,
  task_success_service_request FLOAT64,
  hallucination_rate           FLOAT64,
  latency_p50_ms               INT64,
  latency_p95_ms               INT64,
  cost_per_call_usd            FLOAT64
);

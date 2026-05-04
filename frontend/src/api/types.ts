/**
 * ContactPulse — Frontend ↔ Backend API contract.
 *
 * These types are the single source of truth for data shapes the frontend
 * consumes. They mirror the BigQuery schemas defined in ARCHITECTURE.md §5,
 * projected to the JSON shape the FastAPI service will return. Fixtures
 * under src/fixtures/ MUST conform to these types — see schemas.ts for the
 * runtime zod equivalents.
 *
 * Mapping notes (BigQuery → JSON):
 *   - TIMESTAMP → string in ISO-8601 form (e.g. "2026-05-01T14:32:11.123Z")
 *   - NUMERIC   → number (USD costs are dollars, latency is milliseconds)
 *   - JSON      → typed event_payload discriminated union
 *
 * Long-format BigQuery rows (e.g. eval_runs has one row per metric) are
 * exposed as both raw rows AND aggregated views — the API does the rollup.
 */

// ─── Customer (ARCHITECTURE.md §5: customers) ────────────────────────────
//
// Production PII posture: no name / email / phone reaches the frontend.
// `display_label` is a server-computed safe string of the form
// "Cust #1042 · Gold" — assembled after redaction at the data boundary.
// `tier` drives badge coloring; the special case "anonymous" is rendered
// only when no customer record is attached (CustomerSummary === null).

export type LoyaltyTier = "bronze" | "silver" | "gold";

/** Tier value the UI may render, including the anonymous case. */
export type DisplayTier = LoyaltyTier | "anonymous";

/** Full customer record. Lives in MOCK_CUSTOMERS until the BQ-backed
 *  /customers endpoint lands. Mirrors the redacted projection a real
 *  contact center would expose to operator-facing UI. */
export interface Customer {
  customer_id: string;
  display_label: string;
  tier: LoyaltyTier;
  lifetime_value_usd: number;
  open_orders: number;
  recent_journey: Journey | null;
}

/** Embedded customer reference inside a TraceSummary or event_payload.
 *  Pre-computed display_label avoids the UI ever inventing one. */
export interface CustomerSummary {
  customer_id: string;
  display_label: string;
  tier: LoyaltyTier;
}

// ─── Order (ARCHITECTURE.md §5: orders) ──────────────────────────────────

export type OrderStatus = "placed" | "shipped" | "delivered" | "returned";

export interface Order {
  order_id: string;
  customer_id: string;
  sku: string;
  quantity: number;
  status: OrderStatus;
  placed_at: string;
  eta: string | null;
}

// ─── Conversation lifecycle (ARCHITECTURE.md §5: conversation_traces) ────

export type Modality = "voice" | "chat";

/**
 * Customer-Experience modality (UI-only). Two modes per CLAUDE.md §14:
 *   - "chat":  text in / text out, fastest path, every eval is chat.
 *   - "voice": realtime conversational voice via Gemini Live (WebSocket).
 *
 * The trace-side `Modality` (`voice` | `chat`) describes how a row was
 * recorded; live conversations land in BigQuery as `modality="voice_live"`
 * (a string field, no schema change). Operator Console filters surface them
 * under "voice".
 */
export type CxModality = "voice" | "chat";

export type Journey =
  | "order_status"
  | "product_qa"
  | "service_request"
  | "escalate"
  | "out_of_scope";

export type Outcome = "contained" | "escalated" | "refused" | "in_progress";

/**
 * Event types emitted during a conversation turn (per ARCHITECTURE.md §4.1
 * request lifecycle). Each maps to a distinct event_payload shape below.
 */
export type EventType =
  | "user_message"
  | "stt"
  | "customer_context"
  | "router"
  | "retrieval"
  | "synthesis"
  | "verification"
  | "escalation"
  | "tts"
  | "agent_response";

// ─── Event payloads (one per EventType) ──────────────────────────────────

export interface UserMessagePayload {
  text: string;
  /** True when DLP / PII redaction ran successfully on this utterance.
   *  Drives the "PII redacted" indicator in the trace drill-down. */
  pii_redacted: boolean;
}

export interface SttPayload {
  audio_duration_ms: number;
  transcript: string;
  confidence: number;
  pii_redacted: boolean;
}

export interface CustomerContextPayload {
  customer: CustomerSummary | null;
  recent_orders_count: number;
  prior_contacts_count: number;
  is_anonymous: boolean;
}

export interface RouterCandidate {
  intent: Journey | "ambiguous";
  score: number;
}

export interface RouterPayload {
  model: string;
  intent: Journey | "ambiguous";
  confidence: number;
  threshold: number;
  reasoning: string;
  candidates: RouterCandidate[];
}

export interface RetrievalPassage {
  passage_id: string;
  source: string;
  content: string;
  semantic_score: number;
  keyword_score: number;
  fused_score: number;
  rerank_score: number;
}

export interface RetrievalPayload {
  query: string;
  k: number;
  passages: RetrievalPassage[];
}

export interface SynthesisCitation {
  passage_id: string;
  span: string;
}

export interface SynthesisPayload {
  model: string;
  attempt: number;
  response_text: string;
  citations: SynthesisCitation[];
}

export type VerificationVerdict = "pass" | "fail";

export interface UngroundedClaim {
  claim: string;
  reason: string;
}

export interface VerificationPayload {
  model: string;
  attempt: number;
  verdict: VerificationVerdict;
  score: number;
  threshold: number;
  rationale: string;
  ungrounded_claims: UngroundedClaim[];
}

export type EscalationReason =
  | "low_confidence"
  | "grounding_failed"
  | "explicit_request"
  | "out_of_scope"
  | "turn_cap";

export interface EscalationPayload {
  reason: EscalationReason;
  detail: string;
}

export interface TtsPayload {
  voice: string;
  audio_duration_ms: number;
  audio_url: string;
}

export interface AgentResponsePayload {
  text: string;
  audio_url?: string;
}

// ─── TraceEvent: discriminated union over event_type ─────────────────────

interface TraceEventBase {
  trace_id: string;
  turn_index: number;
  timestamp: string;
  modality: Modality;
  latency_ms: number;
  llm_input_tokens: number;
  llm_output_tokens: number;
  llm_cost_usd: number;
}

export type TraceEvent =
  | (TraceEventBase & { event_type: "user_message"; event_payload: UserMessagePayload })
  | (TraceEventBase & { event_type: "stt"; event_payload: SttPayload })
  | (TraceEventBase & { event_type: "customer_context"; event_payload: CustomerContextPayload })
  | (TraceEventBase & { event_type: "router"; event_payload: RouterPayload })
  | (TraceEventBase & { event_type: "retrieval"; event_payload: RetrievalPayload })
  | (TraceEventBase & { event_type: "synthesis"; event_payload: SynthesisPayload })
  | (TraceEventBase & { event_type: "verification"; event_payload: VerificationPayload })
  | (TraceEventBase & { event_type: "escalation"; event_payload: EscalationPayload })
  | (TraceEventBase & { event_type: "tts"; event_payload: TtsPayload })
  | (TraceEventBase & { event_type: "agent_response"; event_payload: AgentResponsePayload });

// ─── Trace summary (GET /traces) and detail (GET /traces/{id}) ───────────

export interface TraceSummary {
  trace_id: string;
  started_at: string;
  modality: Modality;
  customer: CustomerSummary | null;
  intent: Journey | "ambiguous" | null;
  journey: Journey | null;
  outcome: Outcome;
  turn_count: number;
  total_latency_ms: number;
  total_cost_usd: number;
}

export interface TraceDetail extends TraceSummary {
  ended_at: string | null;
  events: TraceEvent[];
}

// ─── Eval runs (ARCHITECTURE.md §5: eval_runs — long-format) ─────────────

/**
 * Raw long-format row from BigQuery. One row per (run_id, metric_name, journey).
 * The API returns these alongside aggregated summaries; UI prefers summaries.
 */
export interface EvalRunMetricRow {
  run_id: string;
  run_timestamp: string;
  git_sha: string;
  config_hash: string;
  metric_name: string;
  metric_value: number;
  journey: Journey | null;
}

export interface EvalRunPrimaryMetrics {
  containment: number;
  // Label-dependent metrics — null on production rows because production
  // conversations have no ground truth (matches backend Pydantic model).
  refusal_precision: number | null;
  intent_accuracy: number | null;
  retrieval_hit_rate_at_5: number | null;
  hallucination_rate_post_verifier: number | null;
  latency_p95_ms: number | null;
  cost_per_call_usd: number | null;
}

export type EvalRunSource = "golden" | "production";
export type SampleModality = "voice" | "chat" | "all";

export interface EvalRunPerJourney {
  journey: Journey;
  task_success: number;
  query_count: number;
}

export interface EvalRunSummary {
  run_id: string;
  run_timestamp: string;
  git_sha: string;
  config_hash: string;
  total_queries: number;
  source: EvalRunSource;
  sample_modality: SampleModality | null;
  primary_metrics: EvalRunPrimaryMetrics;
}

export interface EvalRunDetail extends EvalRunSummary {
  per_journey: EvalRunPerJourney[];
  rows: EvalRunMetricRow[];
}

// ─── Error clusters (GET /errors/clusters) ───────────────────────────────

export type FailureType =
  | "router_misroute"
  | "retrieval_miss"
  | "grounding_rejection"
  | "over_eager_refusal"
  | "lost_context"
  | "tool_error";

/** Channel scope for an error cluster. "both" surfaces under either filter. */
export type ClusterModality = "voice" | "chat" | "both";

export interface ErrorCluster {
  cluster_id: string;
  label: string;
  failure_type: FailureType;
  /** Defaults to "both" on legacy clusters that haven't been tagged yet. */
  modality: ClusterModality;
  count: number;
  description: string;
  sample_trace_ids: string[];
}

/** Operator Console page-level filter — voice / chat / all. */
export type ChannelFilter = "voice" | "chat" | "all";

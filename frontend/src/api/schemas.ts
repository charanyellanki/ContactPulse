/**
 * Runtime zod schemas mirroring src/api/types.ts.
 *
 * The types file is the contract; this file enforces it at runtime so that
 * fixtures (and, later, real HTTP responses) are validated before they reach
 * UI code. If the backend drifts, parsing fails loud rather than rendering
 * `undefined.something` deep in a component.
 */
import { z } from "zod";

export const loyaltyTierSchema = z.enum(["bronze", "silver", "gold"]);
export const displayTierSchema = z.enum(["bronze", "silver", "gold", "anonymous"]);

export const customerSummarySchema = z.object({
  customer_id: z.string(),
  display_label: z.string(),
  tier: loyaltyTierSchema,
});

export const customerSchema = customerSummarySchema.extend({
  lifetime_value_usd: z.number(),
  open_orders: z.number().int(),
  recent_journey: z
    .enum(["order_status", "product_qa", "service_request", "escalate", "out_of_scope"])
    .nullable(),
});

export const orderStatusSchema = z.enum(["placed", "shipped", "delivered", "returned"]);

export const orderSchema = z.object({
  order_id: z.string(),
  customer_id: z.string(),
  sku: z.string(),
  quantity: z.number().int(),
  status: orderStatusSchema,
  placed_at: z.string(),
  eta: z.string().nullable(),
});

export const modalitySchema = z.enum(["voice", "chat"]);

export const journeySchema = z.enum([
  "order_status",
  "product_qa",
  "service_request",
  "escalate",
  "out_of_scope",
]);

export const outcomeSchema = z.enum(["contained", "escalated", "refused", "in_progress"]);

const intentOrAmbiguousSchema = z.union([journeySchema, z.literal("ambiguous")]);

// ─── Event payloads ──────────────────────────────────────────────────────

const userMessagePayload = z.object({
  text: z.string(),
  pii_redacted: z.boolean(),
});

const sttPayload = z.object({
  audio_duration_ms: z.number(),
  transcript: z.string(),
  confidence: z.number(),
  pii_redacted: z.boolean(),
});

const customerContextPayload = z.object({
  customer: customerSummarySchema.nullable(),
  recent_orders_count: z.number().int(),
  prior_contacts_count: z.number().int(),
  is_anonymous: z.boolean(),
});

const routerCandidate = z.object({
  intent: intentOrAmbiguousSchema,
  score: z.number(),
});

const routerPayload = z.object({
  model: z.string(),
  intent: intentOrAmbiguousSchema,
  confidence: z.number(),
  threshold: z.number(),
  reasoning: z.string(),
  candidates: z.array(routerCandidate),
});

const retrievalPassage = z.object({
  passage_id: z.string(),
  source: z.string(),
  content: z.string(),
  semantic_score: z.number(),
  keyword_score: z.number(),
  fused_score: z.number(),
  rerank_score: z.number(),
});

const retrievalPayload = z.object({
  query: z.string(),
  k: z.number().int(),
  passages: z.array(retrievalPassage),
});

const synthesisCitation = z.object({
  passage_id: z.string(),
  span: z.string(),
});

const synthesisPayload = z.object({
  model: z.string(),
  attempt: z.number().int(),
  response_text: z.string(),
  citations: z.array(synthesisCitation),
});

const ungroundedClaim = z.object({
  claim: z.string(),
  reason: z.string(),
});

const verificationPayload = z.object({
  model: z.string(),
  attempt: z.number().int(),
  verdict: z.enum(["pass", "fail"]),
  score: z.number(),
  threshold: z.number(),
  rationale: z.string(),
  ungrounded_claims: z.array(ungroundedClaim),
});

const escalationPayload = z.object({
  reason: z.enum([
    "low_confidence",
    "grounding_failed",
    "explicit_request",
    "out_of_scope",
    "turn_cap",
  ]),
  detail: z.string(),
});

const ttsPayload = z.object({
  voice: z.string(),
  audio_duration_ms: z.number(),
  audio_url: z.string(),
});

const agentResponsePayload = z.object({
  text: z.string(),
  audio_url: z.string().optional(),
});

// ─── TraceEvent discriminated union ──────────────────────────────────────

const traceEventBase = {
  trace_id: z.string(),
  turn_index: z.number().int(),
  timestamp: z.string(),
  modality: modalitySchema,
  latency_ms: z.number(),
  llm_input_tokens: z.number(),
  llm_output_tokens: z.number(),
  llm_cost_usd: z.number(),
};

export const traceEventSchema = z.discriminatedUnion("event_type", [
  z.object({ ...traceEventBase, event_type: z.literal("user_message"), event_payload: userMessagePayload }),
  z.object({ ...traceEventBase, event_type: z.literal("stt"), event_payload: sttPayload }),
  z.object({ ...traceEventBase, event_type: z.literal("customer_context"), event_payload: customerContextPayload }),
  z.object({ ...traceEventBase, event_type: z.literal("router"), event_payload: routerPayload }),
  z.object({ ...traceEventBase, event_type: z.literal("retrieval"), event_payload: retrievalPayload }),
  z.object({ ...traceEventBase, event_type: z.literal("synthesis"), event_payload: synthesisPayload }),
  z.object({ ...traceEventBase, event_type: z.literal("verification"), event_payload: verificationPayload }),
  z.object({ ...traceEventBase, event_type: z.literal("escalation"), event_payload: escalationPayload }),
  z.object({ ...traceEventBase, event_type: z.literal("tts"), event_payload: ttsPayload }),
  z.object({ ...traceEventBase, event_type: z.literal("agent_response"), event_payload: agentResponsePayload }),
]);

// ─── Trace summary / detail ──────────────────────────────────────────────

export const traceSummarySchema = z.object({
  trace_id: z.string(),
  started_at: z.string(),
  modality: modalitySchema,
  customer: customerSummarySchema.nullable(),
  intent: intentOrAmbiguousSchema.nullable(),
  journey: journeySchema.nullable(),
  outcome: outcomeSchema,
  turn_count: z.number().int(),
  total_latency_ms: z.number(),
  total_cost_usd: z.number(),
});

export const traceDetailSchema = traceSummarySchema.extend({
  ended_at: z.string().nullable(),
  events: z.array(traceEventSchema),
});

export const traceListSchema = z.array(traceSummarySchema);

// ─── Eval runs ───────────────────────────────────────────────────────────

export const evalRunMetricRowSchema = z.object({
  run_id: z.string(),
  run_timestamp: z.string(),
  git_sha: z.string(),
  config_hash: z.string(),
  metric_name: z.string(),
  metric_value: z.number(),
  journey: journeySchema.nullable(),
});

export const evalRunPrimaryMetricsSchema = z.object({
  containment: z.number(),
  refusal_precision: z.number(),
  intent_accuracy: z.number(),
  retrieval_hit_rate_at_5: z.number(),
  hallucination_rate_post_verifier: z.number(),
  latency_p95_ms: z.number(),
  cost_per_call_usd: z.number(),
});

export const evalRunPerJourneySchema = z.object({
  journey: journeySchema,
  task_success: z.number(),
  query_count: z.number().int(),
});

export const evalRunSummarySchema = z.object({
  run_id: z.string(),
  run_timestamp: z.string(),
  git_sha: z.string(),
  config_hash: z.string(),
  total_queries: z.number().int(),
  primary_metrics: evalRunPrimaryMetricsSchema,
});

export const evalRunDetailSchema = evalRunSummarySchema.extend({
  per_journey: z.array(evalRunPerJourneySchema),
  rows: z.array(evalRunMetricRowSchema),
});

export const evalRunListSchema = z.array(evalRunSummarySchema);

// ─── Error clusters ──────────────────────────────────────────────────────

export const failureTypeSchema = z.enum([
  "router_misroute",
  "retrieval_miss",
  "grounding_rejection",
  "over_eager_refusal",
  "lost_context",
  "tool_error",
]);

export const errorClusterSchema = z.object({
  cluster_id: z.string(),
  label: z.string(),
  failure_type: failureTypeSchema,
  count: z.number().int(),
  description: z.string(),
  sample_trace_ids: z.array(z.string()),
});

export const errorClustersSchema = z.array(errorClusterSchema);
export const customersSchema = z.array(customerSchema);

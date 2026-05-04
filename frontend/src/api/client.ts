/**
 * API client — talks to the live FastAPI backend (RUNBOOK §0).
 *
 * Originally this read from JSON fixtures during the UI-first scaffold
 * (CLAUDE.md §2 step 1). Now that the backend is live with BigQuery and
 * Vertex AI wired up, every Operator Console surface should read real data.
 *
 * Trace-detail fallback: a few fixture trace IDs (`trc_001_order_happy`,
 * `trc_002_qa_retry`, `trc_003_escalate`) ship richer event payloads than
 * the live agent currently emits — useful for demoing the full Trace
 * Drill-Down visual without producing perfect synthetic conversations on
 * the fly. We try the backend first; on 404 we fall back to the fixture.
 */
import {
  errorClustersSchema,
  evalRunListSchema,
  traceDetailSchema,
  traceListSchema,
} from "./schemas";
import type {
  Customer,
  ErrorCluster,
  EvalRunSummary,
  SampleModality,
  TraceDetail,
  TraceSummary,
} from "./types";

import { MOCK_CUSTOMERS } from "@/fixtures/mockCustomers";
import trc001 from "@/fixtures/traces/trc_001_order_happy.json";
import trc002 from "@/fixtures/traces/trc_002_qa_retry.json";
import trc003 from "@/fixtures/traces/trc_003_escalate.json";
import { z } from "zod";

const BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
  "http://localhost:8000";

const traceFixtures: Record<string, unknown> = {
  trc_001_order_happy: trc001,
  trc_002_qa_retry: trc002,
  trc_003_escalate: trc003,
};

async function getJson<T>(path: string, schema: z.ZodType<T>): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`GET ${path} failed: ${res.status} ${res.statusText} ${body}`);
  }
  return schema.parse(await res.json());
}

export async function listCustomers(): Promise<Customer[]> {
  // /customers exists on the backend but the frontend currently uses the
  // mock list to keep the customer-selector visuals stable. Wire to backend
  // once the customer endpoint emits the rich CustomerSummary the UI wants.
  return MOCK_CUSTOMERS;
}

export async function listConversations(): Promise<TraceSummary[]> {
  return getJson("/traces", traceListSchema) as Promise<TraceSummary[]>;
}

export async function getTrace(traceId: string): Promise<TraceDetail | null> {
  // Try the backend first; if it 404s (e.g. a curated demo trace ID), fall
  // back to the fixture so the demo always has something rich to drill into.
  try {
    const res = await fetch(`${BASE_URL}/traces/${traceId}`);
    if (res.ok) return traceDetailSchema.parse(await res.json());
    if (res.status !== 404) {
      const body = await res.text().catch(() => "");
      throw new Error(`GET /traces/${traceId}: ${res.status} ${body}`);
    }
  } catch (err) {
    console.warn(`backend trace lookup failed for ${traceId}:`, err);
  }
  const raw = traceFixtures[traceId];
  if (!raw) return null;
  return traceDetailSchema.parse(raw);
}

export async function listEvalRuns(): Promise<EvalRunSummary[]> {
  // zod's `.default()` widens output to T but TS occasionally infers
  // `T | undefined` on object-property defaults; runtime guarantees the field
  // is set, so a narrow assertion here matches reality.
  return getJson("/eval/runs", evalRunListSchema) as Promise<EvalRunSummary[]>;
}

export async function listErrorClusters(): Promise<ErrorCluster[]> {
  return getJson("/errors/clusters", errorClustersSchema) as Promise<ErrorCluster[]>;
}

// ─── Production batch eval — UI-triggered ─────────────────────────────────

export interface BatchEvalRequest {
  modality: SampleModality;
  sample_size: number;
  since_hours: number;
}

export interface BatchEvalPreview {
  modality: SampleModality;
  since_at: string | null;
  new_count: number;
}

const batchEvalPreviewSchema = z.object({
  modality: z.enum(["voice", "chat", "all"]),
  since_at: z.string().nullable(),
  new_count: z.number().int(),
});

export async function getBatchEvalPreview(
  modality: SampleModality,
  since_hours = 168,
): Promise<BatchEvalPreview> {
  const url = `${BASE_URL}/eval/batch/preview?modality=${modality}&since_hours=${since_hours}`;
  const res = await fetch(url);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`GET /eval/batch/preview: ${res.status} ${body}`);
  }
  return batchEvalPreviewSchema.parse(await res.json());
}

const batchEvalResponseSchema = z.object({
  status: z.string(),
  sample_size: z.number().int(),
  modality: z.enum(["voice", "chat", "all"]),
  since_hours: z.number().int(),
  message: z.string(),
});

export async function postBatchEval(req: BatchEvalRequest) {
  const res = await fetch(`${BASE_URL}/eval/batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`POST /eval/batch: ${res.status} ${body}`);
  }
  return batchEvalResponseSchema.parse(await res.json());
}

/**
 * API client.
 *
 * For the UI-first scaffold (CLAUDE.md §2 step 1), this client reads from
 * JSON fixtures shipped under src/fixtures/ and validates them through the
 * zod schemas in ./schemas. When the FastAPI backend (step 2) lands, swap
 * the fixture imports for fetch() calls against `import.meta.env.VITE_API_BASE_URL`
 * — the function signatures and zod-validated return types stay the same.
 *
 * Every component goes through this module (CLAUDE.md §5: "Don't fetch
 * directly from components"). Tests can mock the client by replacing this file.
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
  TraceDetail,
  TraceSummary,
} from "./types";

import { MOCK_CUSTOMERS } from "@/fixtures/mockCustomers";
import conversationsFixture from "@/fixtures/conversations.json";
import evalRunsFixture from "@/fixtures/eval_runs.json";
import errorClustersFixture from "@/fixtures/error_clusters.json";
import trc001 from "@/fixtures/traces/trc_001_order_happy.json";
import trc002 from "@/fixtures/traces/trc_002_qa_retry.json";
import trc003 from "@/fixtures/traces/trc_003_escalate.json";

/** Map of trace_id → fixture JSON. Drives GET /traces/{id} in fixture mode. */
const traceFixtures: Record<string, unknown> = {
  trc_001_order_happy: trc001,
  trc_002_qa_retry: trc002,
  trc_003_escalate: trc003,
};

/** Simulated network delay so React Query loading states are visible. */
const FIXTURE_DELAY_MS = 120;

function delay<T>(value: T, ms = FIXTURE_DELAY_MS): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

export async function listCustomers(): Promise<Customer[]> {
  return delay(MOCK_CUSTOMERS);
}

export async function listConversations(): Promise<TraceSummary[]> {
  return delay(traceListSchema.parse(conversationsFixture));
}

export async function getTrace(traceId: string): Promise<TraceDetail | null> {
  const raw = traceFixtures[traceId];
  if (!raw) return delay(null);
  return delay(traceDetailSchema.parse(raw));
}

export async function listEvalRuns(): Promise<EvalRunSummary[]> {
  return delay(evalRunListSchema.parse(evalRunsFixture));
}

export async function listErrorClusters(): Promise<ErrorCluster[]> {
  return delay(errorClustersSchema.parse(errorClustersFixture));
}

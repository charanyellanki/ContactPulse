/**
 * Live-agent API client — calls the FastAPI backend for the Customer
 * Experience surface (chat: POST /agent/turn). Voice is realtime over the
 * `WS /agent/voice/live` WebSocket — see `src/views/CustomerExperience/LiveVoice.tsx`.
 *
 * Kept separate from `client.ts` (which still serves the Operator Console
 * from JSON fixtures) so the live-conversation flow can be wired to a real
 * backend before the rest of the app gives up its fixtures.
 *
 * Base URL: `import.meta.env.VITE_API_BASE_URL` (e.g. http://localhost:8000).
 * Defaults to "http://localhost:8000" for local dev.
 */
import { z } from "zod";
import { journeySchema } from "./schemas";

const BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
  "http://localhost:8000";

const intentOrAmbiguousSchema = z.union([journeySchema, z.literal("ambiguous")]);

const turnHistoryItemSchema = z.object({
  role: z.string(),
  text: z.string(),
});

export const agentResponseSchema = z.object({
  trace_id: z.string(),
  response_text: z.string(),
  intent: intentOrAmbiguousSchema,
  confidence: z.number(),
  grounded: z.boolean(),
  escalate: z.boolean(),
  latency_ms: z.number().int(),
});

export type AgentTurnHistoryItem = z.infer<typeof turnHistoryItemSchema>;
export type AgentResponse = z.infer<typeof agentResponseSchema>;

interface TurnArgs {
  trace_id: string;
  customer_id: string | null;
  utterance: string;
  modality: "chat" | "voice";
  history: AgentTurnHistoryItem[];
}

async function postJson<T>(path: string, body: unknown, schema: z.ZodType<T>): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`POST ${path} failed: ${res.status} ${res.statusText} ${text}`);
  }
  return schema.parse(await res.json());
}

export function postAgentTurn(args: TurnArgs): Promise<AgentResponse> {
  return postJson("/agent/turn", args, agentResponseSchema);
}

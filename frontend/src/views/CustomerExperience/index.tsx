import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ExternalLink, AlertTriangle } from "lucide-react";
import { useUiStore } from "@/store/ui";
import { Badge } from "@/components/ui/badge";
import { generateTraceId } from "@/lib/traceId";
import { postAgentTurn, type AgentTurnHistoryItem } from "@/api/agent";
import { ModalityToggle } from "./ModalityToggle";
import { CustomerSelector } from "./CustomerSelector";
import { Transcript } from "./Transcript";
import { ChatInput } from "./ChatInput";
import { LiveVoice, type LiveTranscriptTurn } from "./LiveVoice";

interface Turn {
  role: "customer" | "agent";
  text: string;
  timestamp: string;
}

export function CustomerExperience() {
  const modality = useUiStore((s) => s.modality);
  const customerId = useUiStore((s) => s.selectedCustomerId);
  const [traceId] = useState(() => generateTraceId());
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const turnsRef = useRef<Turn[]>([]);
  turnsRef.current = turns;

  const buildHistory = (): AgentTurnHistoryItem[] =>
    turnsRef.current.map((t) => ({
      role: t.role === "agent" ? "agent" : "customer",
      text: t.text,
    }));

  const append = (turn: Turn) => setTurns((prev) => [...prev, turn]);

  const sendChat = async (text: string) => {
    if (busy) return;
    setError(null);
    append({ role: "customer", text, timestamp: new Date().toISOString() });
    setBusy(true);
    try {
      const resp = await postAgentTurn({
        trace_id: traceId,
        customer_id: customerId,
        utterance: text,
        modality: "chat",
        history: buildHistory(),
      });
      append({
        role: "agent",
        text: resp.response_text,
        timestamp: new Date().toISOString(),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const onLiveTurn = (turn: LiveTranscriptTurn) =>
    append({
      role: turn.role,
      text: turn.text,
      timestamp: turn.timestamp,
    });

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-8">
      {/* ── Slim header strip ─────────────────────────────────────────── */}
      <header className="flex flex-wrap items-center justify-between gap-3 border-b pb-3">
        <div className="flex items-center gap-3">
          <ModalityToggle />
        </div>
        <Badge variant="outline" className="font-mono text-[10px]">
          trace · {traceId}
        </Badge>
      </header>

      <div>
        <CustomerSelector />
      </div>

      {/* ── Hero ──────────────────────────────────────────────────────── */}
      <section className="flex flex-col items-center gap-6 py-8">
        {modality === "voice" ? (
          <LiveVoice
            traceId={traceId}
            customerId={customerId}
            onTurn={onLiveTurn}
            onError={setError}
          />
        ) : (
          <div className="flex w-full max-w-xl flex-col items-center gap-3">
            <div className="text-center">
              <div className="text-base font-medium tracking-tight">
                Type a message to the agent
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                Same agent pipeline as voice — DLP, routing, grounding,
                escalation. Switch to Voice to talk hands-free.
              </div>
            </div>
            <div className="w-full">
              <ChatInput disabled={busy} onSend={sendChat} />
            </div>
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            <AlertTriangle className="h-3.5 w-3.5" />
            <span>{error}</span>
          </div>
        )}
      </section>

      {/* ── Conversation log ──────────────────────────────────────────── */}
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-[11px] uppercase tracking-wider text-muted-foreground">
            Conversation log
          </h3>
          <span className="text-[10px] text-muted-foreground/70">
            {turns.length} turn{turns.length === 1 ? "" : "s"}
          </span>
        </div>
        <Transcript turns={turns} />
      </section>

      <footer className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          Conversation tied to trace ID{" "}
          <span className="font-mono text-foreground">{traceId}</span>.
        </span>
        <Link
          to="/operator/traces"
          className="inline-flex items-center gap-1 underline-offset-4 hover:text-foreground hover:underline"
        >
          Open in Operator Console
          <ExternalLink className="h-3 w-3" />
        </Link>
      </footer>
    </div>
  );
}

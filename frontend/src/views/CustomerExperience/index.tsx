import { useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ExternalLink, AlertTriangle } from "lucide-react";
import { useUiStore } from "@/store/ui";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { generateTraceId } from "@/lib/traceId";
import {
  postAgentTurn,
  postAgentVoice,
  type AgentTurnHistoryItem,
} from "@/api/agent";
import { ModalityToggle } from "./ModalityToggle";
import { CustomerSelector } from "./CustomerSelector";
import { Transcript } from "./Transcript";
import { ChatInput } from "./ChatInput";
import { PushToTalk } from "./PushToTalk";

interface Turn {
  role: "customer" | "agent";
  text: string;
  timestamp: string;
}

function playBase64Audio(audio_base64: string, mime: string): void {
  const audio = new Audio(`data:${mime};base64,${audio_base64}`);
  void audio.play().catch(() => {
    // Autoplay can be blocked until the first user gesture; for push-to-talk
    // the gesture has already happened, but we still don't want to throw.
  });
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

  const append = (turn: Turn) =>
    setTurns((prev) => [...prev, turn]);

  const sendChat = async (text: string) => {
    if (busy) return;
    setError(null);
    const now = new Date().toISOString();
    append({ role: "customer", text, timestamp: now });
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
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
    } finally {
      setBusy(false);
    }
  };

  const sendVoice = async (audioBase64: string, mime: string) => {
    if (busy) return;
    setError(null);
    setBusy(true);
    try {
      const resp = await postAgentVoice({
        trace_id: traceId,
        customer_id: customerId,
        audio_base64: audioBase64,
        history: buildHistory(),
      });
      const ts = new Date().toISOString();
      append({ role: "customer", text: resp.utterance, timestamp: ts });
      append({
        role: "agent",
        text: resp.response_text,
        timestamp: new Date().toISOString(),
      });
      playBase64Audio(resp.audio_base64, resp.audio_mime);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      // Avoid the unused-var warning for `mime` while keeping the signature
      // future-proof if we ever forward the recorded mime to the backend.
      void mime;
    } finally {
      setBusy(false);
    }
  };

  const subtitle = useMemo(
    () =>
      modality === "voice"
        ? "Voice channel — push-to-talk. Same agent pipeline as chat."
        : "Chat channel — text input. Same agent pipeline as voice.",
    [modality],
  );

  return (
    <div className="grid grid-cols-12 gap-6">
      <aside className="col-span-12 space-y-4 lg:col-span-3">
        <div>
          <h2 className="text-sm font-medium uppercase tracking-wider text-muted-foreground">
            Channel
          </h2>
          <div className="mt-2">
            <ModalityToggle />
          </div>
        </div>
        <CustomerSelector />
      </aside>

      <section className="col-span-12 space-y-4 lg:col-span-9">
        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-4">
            <div>
              <CardTitle>Customer Experience</CardTitle>
              <div className="text-sm text-muted-foreground">{subtitle}</div>
            </div>
            <Badge variant="outline" className="font-mono text-[10px]">
              trace {traceId}
            </Badge>
          </CardHeader>
          <CardContent className="space-y-4">
            <Transcript turns={turns} />
            {error && (
              <div className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                <AlertTriangle className="h-3.5 w-3.5" />
                <span>{error}</span>
              </div>
            )}
            {modality === "chat" ? (
              <ChatInput disabled={busy} onSend={sendChat} />
            ) : (
              <div className="flex items-center justify-between rounded-lg border bg-card px-4 py-3">
                <div className="text-sm text-muted-foreground">
                  Press and hold the mic to capture an utterance.
                </div>
                <PushToTalk
                  busy={busy}
                  onAudio={sendVoice}
                  onError={setError}
                />
              </div>
            )}
          </CardContent>
        </Card>

        <div className="flex items-center justify-between text-xs text-muted-foreground">
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
        </div>
      </section>
    </div>
  );
}

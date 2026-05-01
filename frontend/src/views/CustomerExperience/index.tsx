import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ExternalLink } from "lucide-react";
import { useUiStore } from "@/store/ui";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { generateTraceId } from "@/lib/traceId";
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

export function CustomerExperience() {
  const modality = useUiStore((s) => s.modality);
  const [traceId] = useState(() => generateTraceId());
  const [turns, setTurns] = useState<Turn[]>([]);

  const send = (text: string) => {
    const now = new Date().toISOString();
    setTurns((prev) => [
      ...prev,
      { role: "customer", text, timestamp: now },
      {
        role: "agent",
        text:
          "(scaffold) Backend not wired yet — this is the frontend skeleton from CLAUDE.md §2 step 1. The Operator Console drill-down for trace " +
          traceId +
          " will populate once the FastAPI service is in place.",
        timestamp: new Date(Date.now() + 600).toISOString(),
      },
    ]);
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
            {modality === "chat" ? (
              <ChatInput onSend={send} />
            ) : (
              <div className="flex items-center justify-between rounded-lg border bg-card px-4 py-3">
                <div className="text-sm text-muted-foreground">
                  Press and hold the mic to capture an utterance.
                </div>
                <PushToTalk onUtterance={send} />
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

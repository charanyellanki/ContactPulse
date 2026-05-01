import { ChevronRight } from "lucide-react";
import {
  Brain,
  CircleDot,
  FileSearch,
  GitBranch,
  Headphones,
  Lock,
  MessageSquare,
  PhoneOutgoing,
  ShieldCheck,
  User,
  Volume2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { JsonView } from "@/components/JsonView";
import { useUiStore } from "@/store/ui";
import { formatCostUsd, formatLatency, formatPercent, formatTimeOnly, formatTokens } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { TraceEvent } from "@/api/types";

const ICONS: Record<TraceEvent["event_type"], React.ComponentType<{ className?: string }>> = {
  user_message: User,
  stt: Headphones,
  customer_context: CircleDot,
  router: GitBranch,
  retrieval: FileSearch,
  synthesis: Brain,
  verification: ShieldCheck,
  escalation: PhoneOutgoing,
  tts: Volume2,
  agent_response: MessageSquare,
};

const TITLES: Record<TraceEvent["event_type"], string> = {
  user_message: "User message",
  stt: "Speech-to-Text",
  customer_context: "Customer context",
  router: "Router",
  retrieval: "Retrieval",
  synthesis: "Synthesis",
  verification: "Grounding verifier",
  escalation: "Escalation",
  tts: "Text-to-Speech",
  agent_response: "Agent response",
};

interface Props {
  event: TraceEvent;
  index: number;
}

export function EventCard({ event, index }: Props) {
  const key = `${event.trace_id}:${index}:${event.event_type}`;
  const expanded = useUiStore((s) => s.expandedEventKeys.has(key));
  const toggle = useUiStore((s) => s.toggleEventExpanded);

  const Icon = ICONS[event.event_type];

  return (
    <Collapsible open={expanded} onOpenChange={() => toggle(key)}>
      <div className="rounded-lg border bg-card shadow-sm">
        <CollapsibleTrigger className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-accent/30">
          <ChevronRight
            className={cn(
              "h-4 w-4 shrink-0 text-muted-foreground transition-transform",
              expanded && "rotate-90",
            )}
          />
          <div className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-secondary text-secondary-foreground">
            <Icon className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">{TITLES[event.event_type]}</span>
              <EventHeadline event={event} />
            </div>
            <div className="mt-0.5 flex items-center gap-3 text-[11px] text-muted-foreground">
              <span className="font-mono">{formatTimeOnly(event.timestamp)}</span>
              <span>· {formatLatency(event.latency_ms)}</span>
              {event.llm_input_tokens + event.llm_output_tokens > 0 && (
                <span>
                  · {formatTokens(event.llm_input_tokens)} in / {formatTokens(event.llm_output_tokens)} out
                </span>
              )}
              {event.llm_cost_usd > 0 && <span>· {formatCostUsd(event.llm_cost_usd)}</span>}
            </div>
          </div>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="space-y-3 border-t bg-muted/20 px-4 py-3">
            <EventBody event={event} />
            <div>
              <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                Raw payload
              </div>
              <JsonView value={event.event_payload} />
            </div>
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}

// ─── Headline (tiny inline summary on the collapsed row) ─────────────────

function EventHeadline({ event }: { event: TraceEvent }) {
  switch (event.event_type) {
    case "router":
      return (
        <Badge
          variant={event.event_payload.confidence >= event.event_payload.threshold ? "secondary" : "warning"}
          className="text-[10px] capitalize"
        >
          {event.event_payload.intent.replace(/_/g, " ")} · {formatPercent(event.event_payload.confidence)}
        </Badge>
      );
    case "verification":
      return (
        <Badge
          variant={event.event_payload.verdict === "pass" ? "success" : "destructive"}
          className="text-[10px] uppercase"
        >
          {event.event_payload.verdict} · {formatPercent(event.event_payload.score)}
          {event.event_payload.attempt > 1 && ` · attempt ${event.event_payload.attempt}`}
        </Badge>
      );
    case "synthesis":
      return (
        <Badge variant="outline" className="text-[10px]">
          attempt {event.event_payload.attempt}
        </Badge>
      );
    case "retrieval":
      return (
        <Badge variant="outline" className="text-[10px]">
          {event.event_payload.passages.length} passages
        </Badge>
      );
    case "escalation":
      return (
        <Badge variant="warning" className="text-[10px] capitalize">
          {event.event_payload.reason.replace(/_/g, " ")}
        </Badge>
      );
    case "stt":
      return (
        <Badge variant="outline" className="text-[10px]">
          conf {formatPercent(event.event_payload.confidence)}
        </Badge>
      );
    case "customer_context":
      return event.event_payload.is_anonymous ? (
        <Badge variant="outline" className="text-[10px]">
          anonymous
        </Badge>
      ) : (
        <Badge variant="outline" className="font-mono text-[10px]">
          #{event.event_payload.customer?.customer_id}
        </Badge>
      );
    default:
      return null;
  }
}

// ─── Body (structured rendering, per event type) ─────────────────────────

function EventBody({ event }: { event: TraceEvent }) {
  switch (event.event_type) {
    case "user_message":
      return (
        <div className="space-y-2">
          <Quote>{event.event_payload.text}</Quote>
          {event.event_payload.pii_redacted && <PiiRedactedTag />}
        </div>
      );

    case "stt":
      return (
        <div className="space-y-2">
          <Quote>{event.event_payload.transcript}</Quote>
          {event.event_payload.pii_redacted && <PiiRedactedTag />}
          <Field label="Audio duration" value={formatLatency(event.event_payload.audio_duration_ms)} />
          <Field label="STT confidence" value={formatPercent(event.event_payload.confidence)} />
        </div>
      );

    case "customer_context": {
      const p = event.event_payload;
      if (p.is_anonymous || !p.customer) {
        return <div className="text-sm text-muted-foreground">Anonymous caller — no profile attached.</div>;
      }
      return (
        <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
          <Field label="Customer" value={p.customer.display_label} />
          <Field label="Tier" value={p.customer.tier} />
          <Field label="Recent orders" value={p.recent_orders_count.toString()} />
          <Field label="Prior contacts" value={p.prior_contacts_count.toString()} />
        </div>
      );
    }

    case "router": {
      const p = event.event_payload;
      return (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-3 text-sm">
            <Field label="Intent" value={p.intent} />
            <Field label="Confidence" value={formatPercent(p.confidence)} />
            <Field label="Threshold" value={formatPercent(p.threshold)} />
          </div>
          <div>
            <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Reasoning
            </div>
            <div className="text-sm leading-relaxed">{p.reasoning}</div>
          </div>
          <div>
            <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Candidate distribution
            </div>
            <div className="space-y-1">
              {p.candidates.map((c) => (
                <div key={c.intent} className="flex items-center gap-2">
                  <span className="w-32 text-xs capitalize text-muted-foreground">
                    {c.intent.replace(/_/g, " ")}
                  </span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-primary"
                      style={{ width: `${Math.min(c.score * 100, 100)}%` }}
                    />
                  </div>
                  <span className="w-12 text-right font-mono text-xs tabular-nums">
                    {c.score.toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
          </div>
          <Field label="Model" value={p.model} mono />
        </div>
      );
    }

    case "retrieval": {
      const p = event.event_payload;
      return (
        <div className="space-y-3">
          <Field label="Query" value={p.query} mono />
          <div className="space-y-2">
            {p.passages.map((passage, idx) => (
              <div key={passage.passage_id} className="rounded-md border bg-background p-3">
                <div className="flex items-baseline justify-between gap-2">
                  <div className="font-mono text-xs text-muted-foreground">
                    #{idx + 1} · {passage.passage_id}
                  </div>
                  <div className="flex gap-2 text-[10px] text-muted-foreground">
                    <span>sem {passage.semantic_score.toFixed(2)}</span>
                    <span>kw {passage.keyword_score.toFixed(2)}</span>
                    <span>fused {passage.fused_score.toFixed(2)}</span>
                    <span className="font-medium text-foreground">
                      rerank {passage.rerank_score.toFixed(2)}
                    </span>
                  </div>
                </div>
                <div className="mt-1 text-xs text-muted-foreground">{passage.source}</div>
                <div className="mt-2 text-sm leading-relaxed">{passage.content}</div>
              </div>
            ))}
          </div>
        </div>
      );
    }

    case "synthesis": {
      const p = event.event_payload;
      return (
        <div className="space-y-2">
          <Quote>{p.response_text}</Quote>
          <Field label="Model" value={p.model} mono />
          <Field label="Attempt" value={p.attempt.toString()} />
          {p.citations.length > 0 && (
            <div>
              <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                Citations
              </div>
              <ul className="space-y-1 text-sm">
                {p.citations.map((c, i) => (
                  <li key={i} className="rounded-md border bg-background p-2">
                    <div className="font-mono text-xs text-muted-foreground">{c.passage_id}</div>
                    <div className="mt-1">{c.span}</div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      );
    }

    case "verification": {
      const p = event.event_payload;
      return (
        <div className="space-y-2">
          <div className="grid grid-cols-3 gap-3 text-sm">
            <Field label="Verdict" value={p.verdict.toUpperCase()} />
            <Field label="Score" value={formatPercent(p.score)} />
            <Field label="Threshold" value={formatPercent(p.threshold)} />
          </div>
          <div>
            <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Rationale
            </div>
            <div className="text-sm leading-relaxed">{p.rationale}</div>
          </div>
          {p.ungrounded_claims.length > 0 && (
            <div>
              <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-destructive">
                Ungrounded claims ({p.ungrounded_claims.length})
              </div>
              <ul className="space-y-1 text-sm">
                {p.ungrounded_claims.map((c, i) => (
                  <li key={i} className="rounded-md border border-destructive/30 bg-destructive/5 p-2">
                    <div className="font-medium">{c.claim}</div>
                    <div className="mt-1 text-xs text-muted-foreground">{c.reason}</div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      );
    }

    case "escalation":
      return (
        <div className="space-y-2 text-sm">
          <Field label="Reason" value={event.event_payload.reason.replace(/_/g, " ")} />
          <div className="leading-relaxed">{event.event_payload.detail}</div>
        </div>
      );

    case "tts":
      return (
        <div className="space-y-1 text-sm">
          <Field label="Voice" value={event.event_payload.voice} mono />
          <Field label="Audio duration" value={formatLatency(event.event_payload.audio_duration_ms)} />
          <Field label="Audio URL" value={event.event_payload.audio_url} mono />
        </div>
      );

    case "agent_response":
      return <Quote>{event.event_payload.text}</Quote>;
  }
}

// ─── Tiny presentation helpers ───────────────────────────────────────────

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className={cn("text-sm", mono && "break-all font-mono text-xs")}>{value}</div>
    </div>
  );
}

function Quote({ children }: { children: React.ReactNode }) {
  return (
    <blockquote className="rounded-md border-l-2 border-primary/40 bg-background px-3 py-2 text-sm leading-relaxed">
      {children}
    </blockquote>
  );
}

/** Inline indicator that DLP / PII redaction ran on this utterance before
 *  it reached downstream agents. The boolean source-of-truth lives on the
 *  payload so when the backend wires up, this stays bound to the same flag. */
function PiiRedactedTag() {
  return (
    <div className="inline-flex items-center gap-1.5 text-xs italic text-muted-foreground">
      <Lock className="h-3 w-3" />
      PII redacted before agent ingestion
    </div>
  );
}

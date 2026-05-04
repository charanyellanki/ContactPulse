import { useEffect, useMemo } from "react";
import { useConversations, useTrace } from "@/api/queries";
import { useUiStore } from "@/store/ui";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { MetricCard } from "@/components/MetricCard";
import { formatCostUsd, formatLatency, formatTimestamp } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Outcome } from "@/api/types";
import { EventCard } from "./EventCard";

const outcomeVariant: Record<Outcome, "success" | "warning" | "destructive" | "secondary"> = {
  contained: "success",
  escalated: "warning",
  refused: "destructive",
  in_progress: "secondary",
};

const FULLY_POPULATED = ["trc_001_order_happy", "trc_002_qa_retry", "trc_003_escalate"];

export function TraceDrillDown() {
  const selectedTraceId = useUiStore((s) => s.selectedTraceId);
  const selectTrace = useUiStore((s) => s.selectTrace);
  const expandAll = useUiStore((s) => s.expandAllEvents);
  const collapseAll = useUiStore((s) => s.collapseAllEvents);

  const channel = useUiStore((s) => s.ocChannelFilter);
  const { data: conversations } = useConversations();
  const { data: trace, isLoading } = useTrace(selectedTraceId);

  const sidebarConversations = useMemo(() => {
    if (!conversations) return [];
    if (channel === "all") return conversations;
    return conversations.filter((c) => c.modality === channel);
  }, [conversations, channel]);

  // Default-select the first matching trace when nothing is chosen, or when
  // the current selection is hidden by the channel filter.
  useEffect(() => {
    if (!conversations) return;
    const stillVisible =
      selectedTraceId && sidebarConversations.some((c) => c.trace_id === selectedTraceId);
    if (!stillVisible && sidebarConversations.length > 0) {
      selectTrace(sidebarConversations[0].trace_id);
    }
  }, [selectedTraceId, conversations, sidebarConversations, selectTrace]);

  const eventKeys = useMemo(() => {
    if (!trace) return [];
    return trace.events.map((e, i) => `${e.trace_id}:${i}:${e.event_type}`);
  }, [trace]);

  return (
    <div className="grid grid-cols-12 gap-6">
      <aside className="col-span-12 lg:col-span-3">
        <Card>
          <CardContent className="p-2">
            <div className="px-2 py-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Conversations
            </div>
            <div className="space-y-0.5">
              {sidebarConversations.length === 0 && (
                <div className="px-2 py-3 text-[11px] text-muted-foreground">
                  No {channel} conversations match the current filter.
                </div>
              )}
              {sidebarConversations.map((c) => {
                const detailed = FULLY_POPULATED.includes(c.trace_id);
                return (
                  <button
                    key={c.trace_id}
                    type="button"
                    onClick={() => selectTrace(c.trace_id)}
                    className={cn(
                      "block w-full rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent",
                      selectedTraceId === c.trace_id && "bg-secondary text-secondary-foreground",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-mono">{c.trace_id}</span>
                      <Badge variant={outcomeVariant[c.outcome]} className="text-[9px] capitalize">
                        {c.outcome}
                      </Badge>
                    </div>
                    <div className="mt-0.5 flex items-center justify-between text-[10px] text-muted-foreground">
                      <span>{c.customer ? `Cust #${c.customer.customer_id}` : "anonymous"}</span>
                      {detailed && <span className="italic">full</span>}
                    </div>
                  </button>
                );
              })}
            </div>
          </CardContent>
        </Card>
      </aside>

      <section className="col-span-12 space-y-4 lg:col-span-9">
        {isLoading && <Skeleton className="h-64 w-full" />}

        {!isLoading && !trace && (
          <Card>
            <CardContent className="grid h-48 place-items-center text-sm text-muted-foreground">
              {selectedTraceId
                ? `No detailed payload available for ${selectedTraceId}. Pick a trace tagged "full" in the sidebar.`
                : "Select a conversation from the sidebar."}
            </CardContent>
          </Card>
        )}

        {trace && (
          <>
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="font-mono text-sm text-muted-foreground">{trace.trace_id}</div>
                <div className="mt-1 flex items-center gap-2">
                  <Badge variant={outcomeVariant[trace.outcome]} className="capitalize">
                    {trace.outcome.replace(/_/g, " ")}
                  </Badge>
                  <Badge variant="outline" className="capitalize">
                    {trace.modality}
                  </Badge>
                  {trace.journey && (
                    <Badge variant="outline" className="capitalize">
                      {trace.journey.replace(/_/g, " ")}
                    </Badge>
                  )}
                  <span className="text-xs text-muted-foreground">
                    started {formatTimestamp(trace.started_at)}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => expandAll(eventKeys)}>
                  Expand all
                </Button>
                <Button variant="outline" size="sm" onClick={() => collapseAll()}>
                  Collapse all
                </Button>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <MetricCard
                label="Customer"
                value={trace.customer ? `Cust #${trace.customer.customer_id}` : "Anonymous"}
                hint={trace.customer ? trace.customer.tier : "no profile"}
              />
              <MetricCard label="Turns" value={trace.turn_count.toString()} />
              <MetricCard label="Total latency" value={formatLatency(trace.total_latency_ms)} />
              <MetricCard label="Total cost" value={formatCostUsd(trace.total_cost_usd)} />
            </div>

            <div className="space-y-2">
              {trace.events.map((event, i) => (
                <EventCard key={i} event={event} index={i} />
              ))}
            </div>
          </>
        )}
      </section>
    </div>
  );
}

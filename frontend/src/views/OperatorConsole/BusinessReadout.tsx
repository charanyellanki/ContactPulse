import { useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useConversations, useEvalRuns } from "@/api/queries";
import { useUiStore } from "@/store/ui";
import { Skeleton } from "@/components/ui/skeleton";
import { MetricCard } from "@/components/MetricCard";
import { formatPercent } from "@/lib/format";

const VOLUME_BY_CHANNEL: Record<"voice" | "chat" | "all", number> = {
  voice:   60_000_000,    // ~60M voice contacts/year — large home-improvement retailer
  chat:    40_000_000,    // ~40M chat contacts/year (digital + in-app)
  all:    100_000_000,    // headline annual contact volume
};

const HANDLE_COST_PER_MIN = 0.85;       // $/agent-minute, loaded
const VOICE_HANDLE_MINUTES = 6;          // avg voice AHT
const CHAT_HANDLE_MINUTES = 4;           // avg chat handle time (concurrent agents)

export function BusinessReadout() {
  const { data: runs, isLoading: runsLoading } = useEvalRuns();
  const { data: conversations, isLoading: convLoading } = useConversations();
  const channel = useUiStore((s) => s.ocChannelFilter);

  // Live cohort containment — recomputed from the filtered conversation list
  // so the Business Readout reflects the active channel scope, not a global
  // average that hides voice-vs-chat gaps.
  const cohortContainment = useMemo(() => {
    if (!conversations) return null;
    const scoped = channel === "all"
      ? conversations
      : conversations.filter((c) => c.modality === channel);
    if (scoped.length === 0) return null;
    const contained = scoped.filter((c) => c.outcome === "contained").length;
    return { rate: contained / scoped.length, n: scoped.length };
  }, [conversations, channel]);

  if (runsLoading || convLoading || !runs) return <Skeleton className="h-64 w-full" />;
  const latest = runs[0];

  // Containment number used for the math — prefer the live cohort rate (true
  // to the channel filter) and fall back to the eval run when no conversations
  // are seeded yet.
  const containment = cohortContainment?.rate ?? latest.primary_metrics.containment;
  const containmentSource = cohortContainment ? `live (${cohortContainment.n} traces)` : "latest eval";

  const callVolume = VOLUME_BY_CHANNEL[channel];
  const containedCalls = Math.round(containment * callVolume);
  const handleMinutes = channel === "chat" ? CHAT_HANDLE_MINUTES : VOICE_HANDLE_MINUTES;
  const associateCostPerCall = HANDLE_COST_PER_MIN * handleMinutes;
  // `cost_per_call_usd` is null on production-source runs (no labels). Fall
  // back to the conservative ARCHITECTURE §12 estimate for the math.
  const llmCostPerCall = latest.primary_metrics.cost_per_call_usd ?? 0.0014;
  const displacedCost = containedCalls * (associateCostPerCall - llmCostPerCall);

  const channelLabel = channel === "all" ? "Voice + Chat" : channel === "voice" ? "Voice" : "Chat";

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <MetricCard
          label={`Annual ${channelLabel.toLowerCase()} volume (modeled)`}
          value={callVolume.toLocaleString()}
          hint={`assumes ${handleMinutes} min avg handle time`}
        />
        <MetricCard
          label="Contained at current rate"
          value={containedCalls.toLocaleString()}
          hint={`${formatPercent(containment)} containment · ${containmentSource}`}
          tone="success"
        />
        <MetricCard
          label="Displaced handle-time cost"
          value={`$${(displacedCost / 1_000_000).toFixed(1)}M`}
          hint={`vs. $${associateCostPerCall.toFixed(2)} associate cost/call`}
          tone="success"
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Looker Studio dashboard (embedded)</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid h-72 place-items-center rounded-md border border-dashed bg-muted/40 text-sm text-muted-foreground">
            Looker iframe will render here once VITE_LOOKER_EMBED_URL is configured (RUNBOOK §6).
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Commentary — {channelLabel} channel</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm leading-relaxed text-muted-foreground">
          <p>
            At a modeled annual {channelLabel.toLowerCase()} volume of{" "}
            {callVolume.toLocaleString()} interactions, the current containment rate of{" "}
            <span className="font-medium text-foreground">{formatPercent(containment)}</span> (
            {containmentSource}) translates to roughly {containedCalls.toLocaleString()}{" "}
            conversations resolved without an associate. Net of LLM cost (
            {formatPercent(llmCostPerCall / associateCostPerCall, 2)} of one associate-touch),
            that displaces approximately ${(displacedCost / 1_000_000).toFixed(1)}M in associate
            handle time per year for this channel alone.
          </p>
          <p>
            The guardrail metric — refusal precision — sits at{" "}
            {latest.primary_metrics.refusal_precision != null
              ? formatPercent(latest.primary_metrics.refusal_precision)
              : "— (production source — labels required)"}
            . When the system says "I don't know," it is correct that often. This is the metric
            that prevents containment from being gamed by confident hallucination, and it is the
            signal a CX data scientist tracks before approving a containment-lifting prompt change.
          </p>
          {channel === "voice" && (
            <p>
              Voice-specific cost levers a data scientist would surface: time-to-first-audio
              from the Gemini Live session (the perceived-latency proxy on a streaming model);
              session duration distribution vs. the per-session ceiling; per-turn count and
              barge-in rate; and Live token usage per session as the cost signal (audio in,
              audio out, and tool-call tokens are billed separately).
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

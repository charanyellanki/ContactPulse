import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useEvalRuns } from "@/api/queries";
import { Skeleton } from "@/components/ui/skeleton";
import { MetricCard } from "@/components/MetricCard";
import { formatPercent } from "@/lib/format";

export function BusinessReadout() {
  const { data, isLoading } = useEvalRuns();
  if (isLoading || !data) return <Skeleton className="h-64 w-full" />;
  const latest = data[0];

  // Back-of-envelope from ARCHITECTURE.md §12: associate handle time at
  // ~$0.50/min × 5 min = $2.50/call; LLM cost per call ~$0.0014.
  const callVolume = 1_000_000;
  const containedCalls = Math.round(latest.primary_metrics.containment * callVolume);
  const associateCostPerCall = 2.5;
  const llmCostPerCall = latest.primary_metrics.cost_per_call_usd;
  const displacedCost = containedCalls * (associateCostPerCall - llmCostPerCall);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <MetricCard
          label="Annual call volume (modeled)"
          value={callVolume.toLocaleString()}
          hint="retailer-scale assumption"
        />
        <MetricCard
          label="Contained at current rate"
          value={containedCalls.toLocaleString()}
          hint={formatPercent(latest.primary_metrics.containment) + " containment"}
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
          <CardTitle>Commentary</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm leading-relaxed text-muted-foreground">
          <p>
            At a modeled annual call volume of {callVolume.toLocaleString()} interactions, the
            current containment rate of {formatPercent(latest.primary_metrics.containment)} translates
            to roughly {containedCalls.toLocaleString()} conversations resolved without an associate.
            Net of LLM cost ({formatPercent(latest.primary_metrics.cost_per_call_usd / associateCostPerCall, 2)}{" "}
            of one associate-touch), that displaces approximately ${(displacedCost / 1_000_000).toFixed(1)}M
            in associate handle time per year.
          </p>
          <p>
            The guardrail metric — refusal precision — sits at{" "}
            {formatPercent(latest.primary_metrics.refusal_precision)}. When the system says "I don't
            know," it is correct that often. This is the metric that prevents containment from being
            gamed by confident hallucination.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

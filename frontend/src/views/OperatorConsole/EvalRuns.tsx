import { useEvalRuns } from "@/api/queries";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { MetricCard } from "@/components/MetricCard";
import { Sparkline } from "@/components/Sparkline";
import { formatCostUsd, formatLatency, formatPercent, formatTimestamp } from "@/lib/format";

export function EvalRuns() {
  const { data, isLoading } = useEvalRuns();

  if (isLoading || !data) return <Skeleton className="h-64 w-full" />;

  // Newest first in the data; reverse for trend lines (oldest → newest).
  const trend = [...data].reverse();
  const containmentSeries = trend.map((r) => r.primary_metrics.containment);
  const refusalSeries = trend.map((r) => r.primary_metrics.refusal_precision);
  const intentSeries = trend.map((r) => r.primary_metrics.intent_accuracy);
  const halluSeries = trend.map((r) => r.primary_metrics.hallucination_rate_post_verifier);
  const latest = data[0];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricCard
          label="Containment"
          value={formatPercent(latest.primary_metrics.containment)}
          hint={`target ≥ 60%`}
          tone={latest.primary_metrics.containment >= 0.6 ? "success" : "warning"}
        />
        <MetricCard
          label="Refusal precision"
          value={formatPercent(latest.primary_metrics.refusal_precision)}
          hint="primary guardrail"
          tone={latest.primary_metrics.refusal_precision >= 0.85 ? "success" : "warning"}
        />
        <MetricCard
          label="Hallucination (post-verifier)"
          value={formatPercent(latest.primary_metrics.hallucination_rate_post_verifier)}
          hint="target ≤ 5%"
          tone={latest.primary_metrics.hallucination_rate_post_verifier <= 0.05 ? "success" : "danger"}
        />
        <MetricCard
          label="p95 latency"
          value={formatLatency(latest.primary_metrics.latency_p95_ms)}
          hint="target ≤ 4s"
          tone={latest.primary_metrics.latency_p95_ms <= 4000 ? "success" : "warning"}
        />
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Run</TableHead>
                <TableHead>Git SHA</TableHead>
                <TableHead className="text-right">Queries</TableHead>
                <TableHead className="text-right">Containment</TableHead>
                <TableHead className="text-right">Refusal precision</TableHead>
                <TableHead className="text-right">Intent acc.</TableHead>
                <TableHead className="text-right">Hallu. rate</TableHead>
                <TableHead className="text-right">Cost / call</TableHead>
                <TableHead>Trend</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((run, i) => {
                const isLatest = i === 0;
                return (
                  <TableRow key={run.run_id}>
                    <TableCell>
                      <div className="font-mono text-xs">{run.run_id}</div>
                      <div className="text-[10px] text-muted-foreground">
                        {formatTimestamp(run.run_timestamp)}
                      </div>
                    </TableCell>
                    <TableCell className="font-mono text-xs">{run.git_sha}</TableCell>
                    <TableCell className="text-right tabular-nums text-sm">{run.total_queries}</TableCell>
                    <TableCell className="text-right tabular-nums text-sm">
                      {formatPercent(run.primary_metrics.containment)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-sm">
                      {formatPercent(run.primary_metrics.refusal_precision)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-sm">
                      {formatPercent(run.primary_metrics.intent_accuracy)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-sm">
                      {formatPercent(run.primary_metrics.hallucination_rate_post_verifier)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-sm">
                      {formatCostUsd(run.primary_metrics.cost_per_call_usd)}
                    </TableCell>
                    <TableCell>
                      {isLatest && (
                        <div className="flex flex-col gap-0.5">
                          <Sparkline values={containmentSeries} />
                          <div className="flex gap-3 text-[9px] uppercase text-muted-foreground">
                            <span>contain</span>
                          </div>
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <TrendCard label="Refusal precision" series={refusalSeries} />
        <TrendCard label="Intent accuracy" series={intentSeries} />
        <TrendCard label="Hallucination rate" series={halluSeries} invert />
      </div>
    </div>
  );
}

function TrendCard({ label, series, invert }: { label: string; series: number[]; invert?: boolean }) {
  return (
    <Card>
      <CardContent className="flex items-center justify-between gap-4 p-4">
        <div>
          <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            {label}
          </div>
          <div className="text-lg font-semibold tabular-nums">
            {formatPercent(series[series.length - 1])}
          </div>
          <div className="text-[10px] text-muted-foreground">
            from {formatPercent(series[0])} · {series.length} runs
          </div>
        </div>
        <Sparkline values={series} width={120} height={36} invert={invert} />
      </CardContent>
    </Card>
  );
}

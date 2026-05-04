import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useBatchEvalPreview, useEvalRuns, queryKeys } from "@/api/queries";
import { useUiStore } from "@/store/ui";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { MetricCard } from "@/components/MetricCard";
import { Sparkline } from "@/components/Sparkline";
import { formatCostUsd, formatLatency, formatPercent, formatTimestamp } from "@/lib/format";
import { Headphones, Play, Loader2 } from "lucide-react";
import { Link } from "react-router-dom";
import { postBatchEval } from "@/api/client";
import type { SampleModality } from "@/api/types";

const NA_STR = "—";
const NA: React.ReactNode = <span className="text-muted-foreground">—</span>;

function pctStr(v: number | null | undefined, dp = 1): string {
  return v == null ? NA_STR : formatPercent(v, dp);
}

function latencyStr(v: number | null | undefined): string {
  return v == null ? NA_STR : formatLatency(v);
}

function pct(v: number | null | undefined, dp = 1): React.ReactNode {
  return v == null ? NA : formatPercent(v, dp);
}

function dollars(v: number | null | undefined): React.ReactNode {
  return v == null ? NA : formatCostUsd(v);
}

export function EvalRuns() {
  const qc = useQueryClient();
  const { data, isLoading } = useEvalRuns();
  const channel = useUiStore((s) => s.ocChannelFilter);

  // Preview the incremental eval — "N new conversations since the last
  // batch run" — so the user can see whether clicking is worth it before
  // they spend Gemini calls.
  const previewModality: SampleModality = channel === "all" ? "all" : channel;
  const { data: preview } = useBatchEvalPreview(previewModality);

  const [batchSize, setBatchSize] = useState(10);
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchToast, setBatchToast] = useState<string | null>(null);

  if (isLoading || !data) return <Skeleton className="h-64 w-full" />;

  const goldenRuns = data.filter((r) => r.source === "golden");
  const productionRuns = data.filter((r) => r.source === "production");
  const trend = [...goldenRuns].reverse(); // sparkline trend across golden runs only
  const containmentSeries = trend.map((r) => r.primary_metrics.containment);
  const refusalSeries = trend
    .map((r) => r.primary_metrics.refusal_precision)
    .filter((x): x is number => x != null);
  const intentSeries = trend
    .map((r) => r.primary_metrics.intent_accuracy)
    .filter((x): x is number => x != null);
  const halluSeries = trend
    .map((r) => r.primary_metrics.hallucination_rate_post_verifier)
    .filter((x): x is number => x != null);

  const latest = goldenRuns[0] ?? data[0];

  const triggerBatch = async () => {
    setBatchRunning(true);
    setBatchToast(null);
    try {
      // Voice / chat / all on the OC filter maps 1:1 to the eval modality
      // filter (the backend accepts the same enum). Defaults to voice.
      const modality: SampleModality = channel === "all" ? "all" : channel;
      const resp = await postBatchEval({
        modality,
        sample_size: batchSize,
        since_hours: 168, // last week — broad enough to catch anything seeded
      });
      setBatchToast(resp.message);
      // Refetch the eval-runs list and the incremental preview a few times.
      // The BackgroundTask typically finishes in 30-60s for sample_size=10.
      const refresh = () => {
        qc.invalidateQueries({ queryKey: queryKeys.evalRuns });
        qc.invalidateQueries({ queryKey: queryKeys.batchPreview(modality) });
      };
      setTimeout(refresh, 5_000);
      setTimeout(refresh, 20_000);
      setTimeout(refresh, 45_000);
      setTimeout(refresh, 75_000);
    } catch (err) {
      setBatchToast(
        err instanceof Error ? `Batch eval failed: ${err.message}` : "Batch eval failed",
      );
    } finally {
      // Clear "running" state after a beat — the actual job is async on the
      // server, but the *trigger* completes immediately.
      setTimeout(() => setBatchRunning(false), 1_000);
    }
  };

  return (
    <div className="space-y-4">
      {/* ── Production batch eval trigger (incremental) ──────────────── */}
      <Card>
        <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1">
            <div className="text-sm font-medium">
              Production batch eval{" "}
              <Badge variant="outline" className="ml-1 text-[10px]">incremental</Badge>
            </div>
            <div className="text-xs text-muted-foreground">
              Judges only conversations created <span className="font-medium text-foreground">since
              the last batch run</span> — no double-counting, no wasted
              Gemini calls. Writes one row to{" "}
              <span className="font-mono">eval_runs</span> tagged{" "}
              <span className="font-mono">source=production</span>. The
              production cadence is Cloud Scheduler → Cloud Run Job hourly;
              this button is the on-demand trigger for the demo.
            </div>
            {preview && (
              <div className="text-xs">
                <span className="font-medium">{preview.new_count}</span>{" "}
                new <span className="font-mono">{preview.modality}</span>{" "}
                conversation{preview.new_count === 1 ? "" : "s"} since{" "}
                <span className="font-mono">
                  {preview.since_at
                    ? new Date(preview.since_at).toLocaleString()
                    : "the cold-start window"}
                </span>
                {preview.new_count === 0 && (
                  <span className="ml-1 text-muted-foreground">
                    — chat in <Link to="/cx" className="underline underline-offset-2">/cx</Link> to generate new traces, then click below.
                  </span>
                )}
              </div>
            )}
          </div>
          <div className="flex flex-shrink-0 items-center gap-2">
            <Badge variant="outline" className="text-[10px]">
              channel: {previewModality}
            </Badge>
            <select
              className="h-8 rounded-md border bg-background px-2 text-xs"
              value={batchSize}
              onChange={(e) => setBatchSize(Number(e.target.value))}
              disabled={batchRunning}
            >
              <option value={5}>up to 5</option>
              <option value={10}>up to 10</option>
              <option value={25}>up to 25</option>
            </select>
            <Button
              onClick={triggerBatch}
              disabled={batchRunning || preview?.new_count === 0}
              size="sm"
            >
              {batchRunning ? (
                <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Play className="mr-2 h-3.5 w-3.5" />
              )}
              {preview && preview.new_count > 0
                ? `Run on ${Math.min(batchSize, preview.new_count)} new`
                : "Run batch eval"}
            </Button>
          </div>
        </CardContent>
        {batchToast && (
          <CardContent className="border-t bg-muted/40 px-4 py-2 text-xs text-muted-foreground">
            {batchToast}
          </CardContent>
        )}
      </Card>

      {channel === "voice" && (
        <Card>
          <CardContent className="flex items-start gap-3 p-3 text-xs">
            <Headphones className="mt-0.5 h-4 w-4 text-muted-foreground" />
            <div className="space-y-0.5 leading-relaxed">
              <div className="font-medium text-foreground">
                Voice channel — eval coverage note
              </div>
              <div className="text-muted-foreground">
                The 150-query labeled smoke set is currently chat-modality.
                Voice quality is tracked at the trace level (Live Conversations
                — Gemini Live session events: user transcripts, tool calls,
                interruptions) and rolled up by the production batch eval above.
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricCard
          label="Containment"
          value={pctStr(latest.primary_metrics.containment)}
          hint={`target ≥ 60%`}
          tone={latest.primary_metrics.containment >= 0.6 ? "success" : "warning"}
        />
        <MetricCard
          label="Refusal precision"
          value={pctStr(latest.primary_metrics.refusal_precision)}
          hint="primary guardrail"
          tone={
            latest.primary_metrics.refusal_precision == null
              ? "default"
              : latest.primary_metrics.refusal_precision >= 0.85
                ? "success"
                : "warning"
          }
        />
        <MetricCard
          label="Hallucination (post-verifier)"
          value={pctStr(latest.primary_metrics.hallucination_rate_post_verifier)}
          hint="target ≤ 5%"
          tone={
            latest.primary_metrics.hallucination_rate_post_verifier == null
              ? "default"
              : latest.primary_metrics.hallucination_rate_post_verifier <= 0.05
                ? "success"
                : "danger"
          }
        />
        <MetricCard
          label="p95 latency"
          value={latencyStr(latest.primary_metrics.latency_p95_ms)}
          hint="target ≤ 4s"
          tone={
            latest.primary_metrics.latency_p95_ms == null
              ? "default"
              : latest.primary_metrics.latency_p95_ms <= 4000
                ? "success"
                : "warning"
          }
        />
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Run</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Git SHA</TableHead>
                <TableHead className="text-right">N</TableHead>
                <TableHead className="text-right">Containment</TableHead>
                <TableHead className="text-right">Refusal precision</TableHead>
                <TableHead className="text-right">Intent acc.</TableHead>
                <TableHead className="text-right">Hallu. rate</TableHead>
                <TableHead className="text-right">Cost / call</TableHead>
                <TableHead>Trend</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((run) => {
                const isLatestGolden = run === goldenRuns[0];
                const sourceLabel = run.source === "production" ? "production" : "golden";
                const modalityLabel = run.sample_modality ?? "—";
                return (
                  <TableRow key={run.run_id}>
                    <TableCell>
                      <div className="font-mono text-xs">{run.run_id}</div>
                      <div className="text-[10px] text-muted-foreground">
                        {formatTimestamp(run.run_timestamp)}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={run.source === "production" ? "warning" : "secondary"}
                        className="text-[10px] capitalize"
                      >
                        {sourceLabel}
                      </Badge>
                      {run.source === "production" && (
                        <div className="mt-0.5 text-[10px] text-muted-foreground">
                          {modalityLabel}
                        </div>
                      )}
                    </TableCell>
                    <TableCell className="font-mono text-xs">{run.git_sha}</TableCell>
                    <TableCell className="text-right tabular-nums text-sm">{run.total_queries}</TableCell>
                    <TableCell className="text-right tabular-nums text-sm">
                      {pct(run.primary_metrics.containment)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-sm">
                      {pct(run.primary_metrics.refusal_precision)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-sm">
                      {pct(run.primary_metrics.intent_accuracy)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-sm">
                      {pct(run.primary_metrics.hallucination_rate_post_verifier)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-sm">
                      {dollars(run.primary_metrics.cost_per_call_usd)}
                    </TableCell>
                    <TableCell>
                      {isLatestGolden && containmentSeries.length >= 2 && (
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

      {productionRuns.length > 0 && (
        <Card>
          <CardContent className="space-y-1 p-3 text-xs">
            <div className="font-medium text-foreground">Production batch eval — methodology note</div>
            <div className="text-muted-foreground">
              Production rows show NULL for label-dependent metrics
              (intent accuracy, refusal precision, retrieval hit-rate) by
              design — production conversations have no ground-truth labels.
              Containment, hallucination, latency, and cost are measured from
              the captured trace + LLM-as-judge rubric. To populate the
              label-dependent metrics, sample N% of production conversations,
              hand-label them, and re-run the golden eval against that slice.
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {refusalSeries.length >= 2 && (
          <TrendCard label="Refusal precision (golden)" series={refusalSeries} />
        )}
        {intentSeries.length >= 2 && (
          <TrendCard label="Intent accuracy (golden)" series={intentSeries} />
        )}
        {halluSeries.length >= 2 && (
          <TrendCard label="Hallucination rate (golden)" series={halluSeries} invert />
        )}
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

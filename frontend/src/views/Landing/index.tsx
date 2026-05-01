import { Link } from "react-router-dom";
import { Activity, ArrowRight, Headphones } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

type PreviewTier = "gold" | "silver" | "bronze" | "anonymous";

interface PreviewRow {
  trace_id: string;
  customer_id: string | null;
  tier: PreviewTier;
  journey: string;
  outcome: "contained" | "escalated" | "refused";
  latency: string;
}

const previewRows: PreviewRow[] = [
  { trace_id: "trc_001_order_happy", customer_id: "1042", tier: "gold",      journey: "order status", outcome: "contained", latency: "1.84s" },
  { trace_id: "trc_002_qa_retry",    customer_id: "2087", tier: "silver",    journey: "product q&a",  outcome: "contained", latency: "4.32s" },
  { trace_id: "trc_003_escalate",    customer_id: null,   tier: "anonymous", journey: "escalate",     outcome: "escalated", latency: "2.42s" },
  { trace_id: "trc_004_service",     customer_id: "4156", tier: "gold",      journey: "service req.", outcome: "contained", latency: "7.24s" },
  { trace_id: "trc_005_qa_refusal",  customer_id: "5203", tier: "silver",    journey: "product q&a",  outcome: "refused",   latency: "3.81s" },
];

const outcomeColor: Record<PreviewRow["outcome"], string> = {
  contained: "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/30",
  escalated: "bg-amber-500/15 text-amber-300 ring-1 ring-amber-500/30",
  refused:   "bg-rose-500/15 text-rose-300 ring-1 ring-rose-500/30",
};

const tierColor: Record<PreviewTier, string> = {
  gold:      "bg-amber-500/15 text-amber-300 ring-1 ring-amber-500/30",
  silver:    "bg-slate-400/15 text-slate-300 ring-1 ring-slate-400/30",
  bronze:    "bg-orange-500/15 text-orange-300 ring-1 ring-orange-500/30",
  anonymous: "bg-white/10 text-white/60 ring-1 ring-white/15",
};

export function Landing() {
  return (
    <div className="grid items-center gap-10 lg:h-[calc(100vh-6.5rem)] lg:grid-cols-2 lg:gap-16">
      {/* ── Left: copy ──────────────────────────────────────────────── */}
      <div className="space-y-7">
        <h1 className="text-4xl font-semibold leading-[1.1] tracking-tight lg:text-5xl">
          Measure, evaluate, and improve contact center AI — in production.
        </h1>
        <p className="max-w-xl text-base leading-relaxed text-muted-foreground">
          ContactPulse is a measurement and improvement framework for production conversational AI agents
          in retail customer experience. The voice and chat agent exists to give the eval harness something
          to measure — the harness, traces, and error analysis are the hero.
        </p>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <Button asChild size="lg" className="w-full justify-between">
              <Link to="/cx">
                <span className="inline-flex items-center gap-2">
                  <Headphones className="h-4 w-4" />
                  Open Customer Experience
                </span>
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <p className="mt-2 text-xs text-muted-foreground">
              The caller-facing voice and chat surface — same agent pipeline either way.
            </p>
          </div>
          <div>
            <Button asChild size="lg" variant="outline" className="w-full justify-between">
              <Link to="/operator">
                <span className="inline-flex items-center gap-2">
                  <Activity className="h-4 w-4" />
                  Open Operator Console
                </span>
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <p className="mt-2 text-xs text-muted-foreground">
              Traces, eval runs, error clusters, and the business readout.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 pt-1">
          <Badge variant="secondary" className="px-3 py-1 text-xs">Real-time traces</Badge>
          <Badge variant="secondary" className="px-3 py-1 text-xs">Eval harness</Badge>
          <Badge variant="secondary" className="px-3 py-1 text-xs">Error analysis</Badge>
        </div>
      </div>

      {/* ── Right: dark preview card ────────────────────────────────── */}
      <Card className="overflow-hidden border-transparent bg-primary text-primary-foreground shadow-2xl">
        <div className="flex items-center justify-between border-b border-white/10 bg-black/30 px-4 py-2.5">
          <div className="flex gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
            <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
            <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
          </div>
          <span className="text-[10px] uppercase tracking-[0.18em] text-white/50">
            Operator Console preview
          </span>
          <span className="w-12" />
        </div>

        <div className="space-y-3 px-5 py-4">
          <div className="flex items-baseline justify-between">
            <h3 className="text-sm font-medium">Live Conversations</h3>
            <span className="text-[10px] text-white/40">refreshed 2s ago · 10 of 152</span>
          </div>

          <div className="rounded-md border border-white/10">
            <div className="grid grid-cols-[1.7fr_1.2fr_1fr_0.9fr_0.6fr] gap-3 border-b border-white/10 px-3 py-2 text-[10px] uppercase tracking-wider text-white/40">
              <span>Trace</span>
              <span>Customer</span>
              <span>Journey</span>
              <span>Outcome</span>
              <span className="text-right">Latency</span>
            </div>
            {previewRows.map((r) => (
              <div
                key={r.trace_id}
                className="grid grid-cols-[1.7fr_1.2fr_1fr_0.9fr_0.6fr] gap-3 border-b border-white/5 px-3 py-2 text-xs last:border-0"
              >
                <span className="truncate font-mono text-white/80">{r.trace_id}</span>
                <span className="flex items-center gap-1.5 truncate">
                  <span className="font-mono text-white/80">
                    {r.customer_id ? `#${r.customer_id}` : "—"}
                  </span>
                  <span className={`inline-flex rounded px-1.5 py-0.5 text-[9px] capitalize ${tierColor[r.tier]}`}>
                    {r.tier}
                  </span>
                </span>
                <span className="truncate text-white/70">{r.journey}</span>
                <span>
                  <span className={`inline-flex rounded-md px-1.5 py-0.5 text-[10px] capitalize ${outcomeColor[r.outcome]}`}>
                    {r.outcome}
                  </span>
                </span>
                <span className="text-right tabular-nums text-white/70">{r.latency}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="border-t border-white/10 bg-black/30 px-5 py-2.5">
          <div className="text-[10px] tracking-wide text-white/50">
            Vertex AI · Gemini 2.0 · BigQuery · Vertex AI Search
          </div>
        </div>
      </Card>
    </div>
  );
}

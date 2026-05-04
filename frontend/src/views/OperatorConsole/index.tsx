import { useNavigate, useParams } from "react-router-dom";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { LiveConversations } from "./LiveConversations";
import { TraceDrillDown } from "./TraceDrillDown";
import { EvalRuns } from "./EvalRuns";
import { ErrorAnalysis } from "./ErrorAnalysis";
import { BusinessReadout } from "./BusinessReadout";
import { ChannelFilter } from "./ChannelFilter";
import { useUiStore } from "@/store/ui";

const TABS = ["traces", "drilldown", "evals", "errors", "readout"] as const;
type Tab = (typeof TABS)[number];

const labels: Record<Tab, string> = {
  traces: "Live Conversations",
  drilldown: "Trace Drill-Down",
  evals: "Eval Runs",
  errors: "Error Analysis",
  readout: "Business Readout",
};

export function OperatorConsole() {
  const navigate = useNavigate();
  const { tab } = useParams<{ tab?: string }>();
  const active: Tab = (TABS as readonly string[]).includes(tab ?? "")
    ? (tab as Tab)
    : "traces";
  const channel = useUiStore((s) => s.ocChannelFilter);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Operator Console</h1>
          <p className="text-sm text-muted-foreground">
            Traces, eval runs, error clusters, and the business readout — the surface a CX data
            scientist actually uses.
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <ChannelFilter />
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
            {channel === "voice"
              ? "scoped to voice"
              : channel === "chat"
                ? "scoped to chat"
                : "all channels"}
          </div>
        </div>
      </div>

      <Tabs value={active} onValueChange={(v) => navigate(`/operator/${v}`)}>
        <TabsList>
          {TABS.map((t) => (
            <TabsTrigger key={t} value={t}>
              {labels[t]}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="traces" className="mt-4">
          <LiveConversations onOpenTrace={() => navigate("/operator/drilldown")} />
        </TabsContent>
        <TabsContent value="drilldown" className="mt-4">
          <TraceDrillDown />
        </TabsContent>
        <TabsContent value="evals" className="mt-4">
          <EvalRuns />
        </TabsContent>
        <TabsContent value="errors" className="mt-4">
          <ErrorAnalysis onOpenTrace={() => navigate("/operator/drilldown")} />
        </TabsContent>
        <TabsContent value="readout" className="mt-4">
          <BusinessReadout />
        </TabsContent>
      </Tabs>
    </div>
  );
}

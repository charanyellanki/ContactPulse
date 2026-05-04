import { useMemo } from "react";
import { useErrorClusters } from "@/api/queries";
import { useUiStore } from "@/store/ui";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { ClusterModality, FailureType } from "@/api/types";

const failureLabel: Record<FailureType, string> = {
  router_misroute: "Router misroute",
  retrieval_miss: "Retrieval miss",
  grounding_rejection: "Grounding rejection",
  over_eager_refusal: "Over-eager refusal",
  lost_context: "Lost context",
  tool_error: "Tool error",
};

const failureVariant: Record<FailureType, "warning" | "destructive" | "secondary"> = {
  router_misroute: "warning",
  retrieval_miss: "warning",
  grounding_rejection: "destructive",
  over_eager_refusal: "warning",
  lost_context: "secondary",
  tool_error: "destructive",
};

const modalityLabel: Record<ClusterModality, string> = {
  voice: "Voice",
  chat: "Chat",
  both: "Voice + Chat",
};

interface Props {
  onOpenTrace: () => void;
}

export function ErrorAnalysis({ onOpenTrace }: Props) {
  const { data, isLoading } = useErrorClusters();
  const selectTrace = useUiStore((s) => s.selectTrace);
  const channel = useUiStore((s) => s.ocChannelFilter);

  const filtered = useMemo(() => {
    if (!data) return [];
    if (channel === "all") return data;
    return data.filter((c) => c.modality === channel || c.modality === "both");
  }, [data, channel]);

  if (isLoading || !data) return <Skeleton className="h-64 w-full" />;

  return (
    <div className="space-y-3">
      {filtered.length === 0 && (
        <Card>
          <CardContent className="grid h-32 place-items-center text-sm text-muted-foreground">
            No clusters tagged for {channel}. Try "All" to see cross-channel clusters.
          </CardContent>
        </Card>
      )}
      {filtered.length > 0 && filtered.map((cluster) => (
        <Card key={cluster.cluster_id}>
          <CardHeader className="flex flex-row items-start justify-between gap-4 pb-2">
            <div className="space-y-1">
              <CardTitle className="text-base">{cluster.label}</CardTitle>
              <div className="flex items-center gap-2">
                <Badge variant={failureVariant[cluster.failure_type]} className="text-[10px]">
                  {failureLabel[cluster.failure_type]}
                </Badge>
                <Badge variant="outline" className="text-[10px]">
                  {modalityLabel[cluster.modality]}
                </Badge>
                <span className="text-xs text-muted-foreground">
                  {cluster.count} conversations affected
                </span>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p className="leading-relaxed text-muted-foreground">{cluster.description}</p>
            {cluster.sample_trace_ids.length > 0 && (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                  Sample traces:
                </span>
                {cluster.sample_trace_ids.map((tid) => (
                  <Button
                    key={tid}
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      selectTrace(tid);
                      onOpenTrace();
                    }}
                    className="font-mono text-xs"
                  >
                    {tid}
                  </Button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

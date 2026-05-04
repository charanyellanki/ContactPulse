import { useMemo } from "react";
import { useConversations } from "@/api/queries";
import { useUiStore } from "@/store/ui";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { TierBadge } from "@/components/TierBadge";
import { formatCostUsd, formatLatency, formatTimestamp } from "@/lib/format";
import type { Outcome, TraceSummary } from "@/api/types";

const outcomeVariant: Record<Outcome, "success" | "warning" | "destructive" | "secondary"> = {
  contained: "success",
  escalated: "warning",
  refused: "destructive",
  in_progress: "secondary",
};

interface Props {
  onOpenTrace: () => void;
}

export function LiveConversations({ onOpenTrace }: Props) {
  const { data, isLoading } = useConversations();
  const selectTrace = useUiStore((s) => s.selectTrace);
  const channel = useUiStore((s) => s.ocChannelFilter);

  const filtered: TraceSummary[] | undefined = useMemo(() => {
    if (!data) return undefined;
    if (channel === "all") return data;
    return data.filter((r) => r.modality === channel);
  }, [data, channel]);

  if (isLoading) {
    return <Skeleton className="h-64 w-full" />;
  }

  if (filtered && filtered.length === 0) {
    return (
      <Card>
        <CardContent className="grid h-32 place-items-center text-sm text-muted-foreground">
          No {channel} conversations in the latest window. Switch channel to "all" to compare across modalities.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Started</TableHead>
              <TableHead>Trace</TableHead>
              <TableHead>Modality</TableHead>
              <TableHead>Customer</TableHead>
              <TableHead>Journey</TableHead>
              <TableHead>Outcome</TableHead>
              <TableHead className="text-right">Turns</TableHead>
              <TableHead className="text-right">Latency</TableHead>
              <TableHead className="text-right">Cost</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered?.map((row) => {
              const detailed = ["trc_001_order_happy", "trc_002_qa_retry", "trc_003_escalate"].includes(
                row.trace_id,
              );
              return (
                <TableRow
                  key={row.trace_id}
                  className="cursor-pointer"
                  onClick={() => {
                    selectTrace(row.trace_id);
                    onOpenTrace();
                  }}
                >
                  <TableCell className="text-xs text-muted-foreground">
                    {formatTimestamp(row.started_at)}
                  </TableCell>
                  <TableCell>
                    <span className="font-mono text-xs">{row.trace_id}</span>
                    {detailed && (
                      <Badge variant="outline" className="ml-2 text-[10px]">
                        full payload
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="capitalize text-sm">{row.modality}</TableCell>
                  <TableCell>
                    {row.customer ? (
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs">#{row.customer.customer_id}</span>
                        <TierBadge tier={row.customer.tier} />
                      </div>
                    ) : (
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs text-muted-foreground">—</span>
                        <TierBadge tier="anonymous" />
                      </div>
                    )}
                  </TableCell>
                  <TableCell className="text-sm">
                    {row.journey ? row.journey.replace(/_/g, " ") : "—"}
                  </TableCell>
                  <TableCell>
                    <Badge variant={outcomeVariant[row.outcome]} className="capitalize">
                      {row.outcome.replace(/_/g, " ")}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-sm">{row.turn_count}</TableCell>
                  <TableCell className="text-right tabular-nums text-sm">
                    {formatLatency(row.total_latency_ms)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-sm">
                    {formatCostUsd(row.total_cost_usd)}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

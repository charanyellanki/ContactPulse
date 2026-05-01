import { useCustomers } from "@/api/queries";
import { useUiStore } from "@/store/ui";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { TierBadge } from "@/components/TierBadge";
import { cn } from "@/lib/utils";

export function CustomerSelector() {
  const { data: customers, isLoading } = useCustomers();
  const selectedId = useUiStore((s) => s.selectedCustomerId);
  const setSelected = useUiStore((s) => s.setSelectedCustomer);

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm">Mock customer</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        <button
          type="button"
          onClick={() => setSelected(null)}
          className={cn(
            "flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent",
            selectedId === null && "bg-secondary text-secondary-foreground",
          )}
        >
          <span className="font-mono text-xs text-muted-foreground">no profile</span>
          <TierBadge tier="anonymous" />
        </button>

        {isLoading && <Skeleton className="h-8 w-full" />}

        {customers?.map((c) => (
          <button
            key={c.customer_id}
            type="button"
            onClick={() => setSelected(c.customer_id)}
            className={cn(
              "flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent",
              selectedId === c.customer_id && "bg-secondary text-secondary-foreground",
            )}
          >
            <span className="font-mono text-xs">Cust #{c.customer_id}</span>
            <TierBadge tier={c.tier} />
          </button>
        ))}
      </CardContent>
    </Card>
  );
}

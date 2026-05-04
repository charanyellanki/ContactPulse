/**
 * CustomerSelector — compact inline pills for the new CX top bar.
 *
 * Used to be a full sidebar card; the v1.4 redesign puts the VoiceOrb at
 * page center and demotes everything else to a slim header strip.
 */
import { useCustomers } from "@/api/queries";
import { useUiStore } from "@/store/ui";
import { TierBadge } from "@/components/TierBadge";
import { cn } from "@/lib/utils";

export function CustomerSelector() {
  const { data: customers, isLoading } = useCustomers();
  const selectedId = useUiStore((s) => s.selectedCustomerId);
  const setSelected = useUiStore((s) => s.setSelectedCustomer);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-[11px] uppercase tracking-wider text-muted-foreground">
        Caller
      </span>
      <button
        type="button"
        onClick={() => setSelected(null)}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors",
          selectedId === null
            ? "border-foreground/40 bg-secondary text-secondary-foreground"
            : "border-border text-muted-foreground hover:bg-accent",
        )}
      >
        <span className="font-mono text-[11px]">anonymous</span>
        <TierBadge tier="anonymous" />
      </button>

      {isLoading && (
        <span className="text-xs text-muted-foreground">loading…</span>
      )}

      {customers?.map((c) => (
        <button
          key={c.customer_id}
          type="button"
          onClick={() => setSelected(c.customer_id)}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors",
            selectedId === c.customer_id
              ? "border-foreground/40 bg-secondary text-secondary-foreground"
              : "border-border text-muted-foreground hover:bg-accent",
          )}
        >
          <span className="font-mono text-[11px]">#{c.customer_id}</span>
          <TierBadge tier={c.tier} />
        </button>
      ))}
    </div>
  );
}

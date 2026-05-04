/**
 * Page-level channel filter for the Operator Console.
 *
 * The role this project targets (CX data scientist, contact-center voice
 * agents) cares primarily about the voice channel. The filter scopes:
 *   - Live Conversations  → only rows with `modality === filter`
 *   - Trace Drill-Down    → sidebar only lists matching traces
 *   - Eval Runs           → notes when the test set is chat-only
 *   - Error Analysis      → only clusters where `cluster.modality` matches
 *                           (or `modality === "both"`)
 *   - Business Readout    → containment math scoped to the filtered cohort
 *
 * "All" is available for cross-channel comparisons but is not the default —
 * voice is, on purpose.
 */
import { Headphones, MessagesSquare, Layers } from "lucide-react";
import { useUiStore } from "@/store/ui";
import { cn } from "@/lib/utils";
import type { ChannelFilter as Filter } from "@/api/types";

const options: { value: Filter; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { value: "voice", label: "Voice", icon: Headphones },
  { value: "chat", label: "Chat", icon: MessagesSquare },
  { value: "all", label: "All", icon: Layers },
];

export function ChannelFilter() {
  const filter = useUiStore((s) => s.ocChannelFilter);
  const setFilter = useUiStore((s) => s.setOcChannelFilter);

  return (
    <div
      role="tablist"
      aria-label="Channel filter"
      className="inline-flex h-9 items-center gap-1 rounded-lg border bg-card p-1 shadow-sm"
    >
      {options.map(({ value, label, icon: Icon }) => {
        const active = filter === value;
        return (
          <button
            key={value}
            role="tab"
            aria-selected={active}
            type="button"
            onClick={() => setFilter(value)}
            className={cn(
              "inline-flex h-7 items-center gap-1.5 rounded-md px-3 text-xs font-medium transition-colors",
              active
                ? "bg-secondary text-secondary-foreground shadow-sm"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </button>
        );
      })}
    </div>
  );
}

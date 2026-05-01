import { cn } from "@/lib/utils";
import type { DisplayTier } from "@/api/types";

/** Centralized tier rendering. Light- and dark-mode tuned color tokens
 *  per tier; the "anonymous" variant covers null-customer cases (callers
 *  with no profile attached). */
const TIER_CLASS: Record<DisplayTier, string> = {
  gold:
    "bg-amber-100 text-amber-900 ring-amber-200 dark:bg-amber-500/15 dark:text-amber-300 dark:ring-amber-500/30",
  silver:
    "bg-slate-100 text-slate-700 ring-slate-200 dark:bg-slate-500/15 dark:text-slate-300 dark:ring-slate-500/30",
  bronze:
    "bg-orange-100 text-orange-900 ring-orange-200 dark:bg-orange-500/15 dark:text-orange-300 dark:ring-orange-500/30",
  anonymous:
    "bg-zinc-100 text-zinc-600 ring-zinc-200 dark:bg-zinc-500/15 dark:text-zinc-400 dark:ring-zinc-500/30",
};

interface Props {
  tier: DisplayTier;
  className?: string;
}

export function TierBadge({ tier, className }: Props) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium capitalize ring-1 ring-inset",
        TIER_CLASS[tier],
        className,
      )}
    >
      {tier}
    </span>
  );
}

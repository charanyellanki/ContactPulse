import { cn } from "@/lib/utils";

interface Props {
  value: unknown;
  className?: string;
}

/** Read-only pretty-printed JSON. Used inside expanded event cards to show
 *  the raw event_payload alongside the structured rendering. */
export function JsonView({ value, className }: Props) {
  return (
    <pre
      className={cn(
        "max-h-80 overflow-auto rounded-md bg-muted/60 px-3 py-2 font-mono text-[11px] leading-relaxed text-foreground",
        className,
      )}
    >
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

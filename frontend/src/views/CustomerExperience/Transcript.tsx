import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface TranscriptTurn {
  role: "customer" | "agent";
  text: string;
  timestamp: string;
}

interface Props {
  turns: TranscriptTurn[];
}

export function Transcript({ turns }: Props) {
  return (
    <Card className="min-h-[320px]">
      <CardContent className="space-y-3 p-4">
        {turns.length === 0 && (
          <div className="grid h-64 place-items-center text-sm text-muted-foreground">
            Conversation will appear here. (Frontend scaffold — backend not yet wired.)
          </div>
        )}
        {turns.map((t, i) => (
          <div
            key={i}
            className={cn(
              "flex flex-col gap-1",
              t.role === "customer" ? "items-end" : "items-start",
            )}
          >
            <div
              className={cn(
                "max-w-[80%] rounded-2xl px-3 py-2 text-sm leading-relaxed shadow-sm",
                t.role === "customer"
                  ? "rounded-br-sm bg-primary text-primary-foreground"
                  : "rounded-bl-sm bg-secondary text-secondary-foreground",
              )}
            >
              {t.text}
            </div>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
              {t.role} · {new Date(t.timestamp).toLocaleTimeString()}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

/**
 * Transcript — a quiet conversation log below the VoiceOrb / ChatInput.
 *
 * The CX surface is voice-first; the transcript is reference, not the
 * spotlight. Layout reflects that: dimmed by default, bubble-light, scrolls
 * upward with the latest turn anchored to the bottom.
 */
import { useEffect, useRef } from "react";
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
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length]);

  if (turns.length === 0) {
    return (
      <div className="text-center text-xs text-muted-foreground/70">
        Conversation log will appear here as you talk.
      </div>
    );
  }

  return (
    <div className="max-h-[260px] space-y-2 overflow-y-auto pr-1">
      {turns.map((t, i) => (
        <div
          key={i}
          className={cn(
            "flex items-start gap-3 text-sm",
            t.role === "customer" ? "justify-end" : "justify-start",
          )}
        >
          {t.role === "agent" && (
            <span className="mt-1 text-[10px] uppercase tracking-wider text-emerald-600">
              agent
            </span>
          )}
          <div
            className={cn(
              "max-w-[80%] rounded-2xl px-3 py-1.5 leading-relaxed",
              t.role === "customer"
                ? "rounded-br-sm bg-primary/10 text-foreground"
                : "rounded-bl-sm bg-muted text-foreground",
            )}
          >
            {t.text}
          </div>
          {t.role === "customer" && (
            <span className="mt-1 text-[10px] uppercase tracking-wider text-muted-foreground">
              caller
            </span>
          )}
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}

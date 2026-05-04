import { MessageSquare, Mic } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useUiStore } from "@/store/ui";
import { cn } from "@/lib/utils";
import type { CxModality } from "@/api/types";

interface ModeDef {
  key: CxModality;
  label: string;
  icon: LucideIcon;
  hint: string;
}

const MODES: ModeDef[] = [
  { key: "voice", label: "Voice", icon: Mic,           hint: "Realtime voice (Gemini Live)" },
  { key: "chat",  label: "Chat",  icon: MessageSquare, hint: "Text in / text out" },
];

export function ModalityToggle() {
  const modality = useUiStore((s) => s.modality);
  const setModality = useUiStore((s) => s.setModality);

  return (
    <div className="inline-flex items-center rounded-lg border bg-card p-0.5">
      {MODES.map(({ key, label, icon: Icon, hint }) => (
        <button
          key={key}
          type="button"
          onClick={() => setModality(key)}
          title={hint}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-md px-3 py-1 text-sm font-medium transition-colors",
            modality === key
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:bg-accent",
          )}
        >
          <Icon className="h-4 w-4" />
          {label}
        </button>
      ))}
    </div>
  );
}

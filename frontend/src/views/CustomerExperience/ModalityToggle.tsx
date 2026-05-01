import { MessageSquare, Mic } from "lucide-react";
import { useUiStore } from "@/store/ui";
import { cn } from "@/lib/utils";

export function ModalityToggle() {
  const modality = useUiStore((s) => s.modality);
  const setModality = useUiStore((s) => s.setModality);

  return (
    <div className="inline-flex items-center rounded-lg border bg-card p-0.5">
      <button
        type="button"
        onClick={() => setModality("voice")}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-md px-3 py-1 text-sm font-medium transition-colors",
          modality === "voice" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-accent",
        )}
      >
        <Mic className="h-4 w-4" />
        Voice
      </button>
      <button
        type="button"
        onClick={() => setModality("chat")}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-md px-3 py-1 text-sm font-medium transition-colors",
          modality === "chat" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-accent",
        )}
      >
        <MessageSquare className="h-4 w-4" />
        Chat
      </button>
    </div>
  );
}

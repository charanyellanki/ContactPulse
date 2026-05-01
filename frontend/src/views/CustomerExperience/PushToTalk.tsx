import { useState } from "react";
import { Mic, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface Props {
  onUtterance: (text: string) => void;
}

/** Push-to-talk stub. The real backend will stream audio to STT; for the
 *  scaffold we simulate by submitting a canned phrase when the user releases. */
export function PushToTalk({ onUtterance }: Props) {
  const [recording, setRecording] = useState(false);

  return (
    <div className="flex flex-col items-center gap-2">
      <Button
        size="lg"
        onMouseDown={() => setRecording(true)}
        onMouseUp={() => {
          setRecording(false);
          onUtterance("(simulated voice utterance — STT not wired in scaffold mode)");
        }}
        onMouseLeave={() => setRecording(false)}
        className={cn(
          "h-16 w-16 rounded-full transition-transform",
          recording && "scale-110 bg-destructive hover:bg-destructive/90",
        )}
      >
        {recording ? <Square className="h-6 w-6" /> : <Mic className="h-6 w-6" />}
      </Button>
      <div className="text-xs text-muted-foreground">
        {recording ? "Recording… release to send" : "Hold to talk"}
      </div>
    </div>
  );
}

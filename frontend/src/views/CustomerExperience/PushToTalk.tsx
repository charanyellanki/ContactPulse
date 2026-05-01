import { useRef, useState } from "react";
import { Mic, Square, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface Props {
  /** Disable while a previous turn is still in flight. */
  busy?: boolean;
  /** Called with base64-encoded audio (no data: prefix) when recording stops. */
  onAudio: (audioBase64: string, mimeType: string) => void;
  /** Optional surface for permission/recording errors. */
  onError?: (message: string) => void;
}

const RECORDER_MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/mp4",
];

function pickSupportedMime(): string {
  if (typeof MediaRecorder === "undefined") return "";
  for (const m of RECORDER_MIME_CANDIDATES) {
    if (MediaRecorder.isTypeSupported(m)) return m;
  }
  return "";
}

async function blobToBase64(blob: Blob): Promise<string> {
  const buf = await blob.arrayBuffer();
  const bytes = new Uint8Array(buf);
  let s = "";
  for (let i = 0; i < bytes.byteLength; i += 0x8000) {
    s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(s);
}

/** Push-to-talk: hold to record, release to POST /agent/voice. */
export function PushToTalk({ busy, onAudio, onError }: Props) {
  const [recording, setRecording] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);

  const stopAndCleanup = () => {
    setRecording(false);
    recorderRef.current?.stop();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    recorderRef.current = null;
  };

  const start = async () => {
    if (busy || recording) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mime = pickSupportedMime();
      const recorder = mime
        ? new MediaRecorder(stream, { mimeType: mime })
        : new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = async () => {
        const type = recorder.mimeType || mime || "audio/webm";
        const blob = new Blob(chunksRef.current, { type });
        chunksRef.current = [];
        if (blob.size === 0) return;
        try {
          const b64 = await blobToBase64(blob);
          onAudio(b64, type);
        } catch (err) {
          onError?.(err instanceof Error ? err.message : "audio encoding failed");
        }
      };
      recorder.start();
      recorderRef.current = recorder;
      setRecording(true);
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "could not access microphone";
      onError?.(msg);
    }
  };

  const stop = () => {
    if (!recording) return;
    stopAndCleanup();
  };

  return (
    <div className="flex flex-col items-center gap-2">
      <Button
        size="lg"
        disabled={busy}
        onMouseDown={start}
        onMouseUp={stop}
        onMouseLeave={stop}
        onTouchStart={start}
        onTouchEnd={stop}
        className={cn(
          "h-16 w-16 rounded-full transition-transform",
          recording && "scale-110 bg-destructive hover:bg-destructive/90",
        )}
      >
        {busy ? (
          <Loader2 className="h-6 w-6 animate-spin" />
        ) : recording ? (
          <Square className="h-6 w-6" />
        ) : (
          <Mic className="h-6 w-6" />
        )}
      </Button>
      <div className="text-xs text-muted-foreground">
        {busy
          ? "Working…"
          : recording
            ? "Recording… release to send"
            : "Hold to talk"}
      </div>
    </div>
  );
}

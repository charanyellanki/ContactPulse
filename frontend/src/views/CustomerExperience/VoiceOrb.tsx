/**
 * VoiceOrb — the centerpiece of the Customer Experience surface.
 *
 * Presentational. Owns no audio or WebSocket state — `LiveVoice` injects
 * `status` + `level` and wires `onStart`/`onStop`. The orb's job is to make
 * the system's state legible at a glance, especially the fact that the
 * conversation is continuous: when the bot finishes speaking, it returns to
 * "listening" without the user having to tap anything.
 *
 * Visual states:
 *   idle        — soft pulse, mic icon, "Tap to start"
 *   connecting  — spinner overlay
 *   listening   — primary-accented breathing rings; scales with mic level
 *   agent       — accent-colored breathing rings; scales with playback level
 *   ending      — spinner overlay
 *   error       — destructive-tinted, idle-style affordance
 */
import { Loader2, Mic } from "lucide-react";
import { cn } from "@/lib/utils";

export type OrbStatus =
  | "idle"
  | "connecting"
  | "listening"
  | "agent"
  | "ending"
  | "error";

interface Props {
  status: OrbStatus;
  /** Smoothed audio level in [0,1] driving the pulse scale. */
  level: number;
  onStart: () => void;
  onStop: () => void;
}

export function VoiceOrb({ status, level, onStart, onStop }: Props) {
  const isActive = status === "listening" || status === "agent";
  const isBusy = status === "connecting" || status === "ending";

  // Scale: idle ≈ 1, active = 1 + boost from current level. We clamp the
  // boost low so the orb breathes rather than jiggles.
  const scale = 1 + (isActive ? Math.min(0.18, level * 0.6) : 0);

  const handleClick = () => {
    if (isBusy) return;
    if (isActive) onStop();
    else onStart();
  };

  const tone = orbTone(status);

  return (
    <div className="flex flex-col items-center gap-6">
      <div className="relative grid place-items-center" style={{ width: 280, height: 280 }}>
        {/* Three slowly-staggered breathing rings — give the "still alive,
            still listening" cue while idle-but-active. */}
        {isActive && (
          <>
            <Ring tone={tone} delayMs={0}    />
            <Ring tone={tone} delayMs={900}  />
            <Ring tone={tone} delayMs={1800} />
          </>
        )}

        <button
          type="button"
          onClick={handleClick}
          disabled={isBusy}
          aria-label={isActive ? "Stop voice session" : "Start voice session"}
          className={cn(
            "relative grid h-44 w-44 place-items-center rounded-full border-2 transition-all duration-200 ease-out",
            "shadow-lg",
            tone.bg,
            tone.border,
            tone.fg,
            !isBusy && "active:scale-[0.98]",
          )}
          style={{ transform: `scale(${scale.toFixed(3)})` }}
        >
          {isBusy ? (
            <Loader2 className="h-14 w-14 animate-spin" />
          ) : (
            <Mic className="h-14 w-14" />
          )}
          {/* Inner highlight to give the orb depth */}
          <span
            aria-hidden
            className="pointer-events-none absolute inset-2 rounded-full opacity-40"
            style={{
              background:
                "radial-gradient(closest-side, rgba(255,255,255,0.35), transparent 70%)",
            }}
          />
        </button>
      </div>

      {/* aria-live so a screen reader announces idle → listening → agent
          → error transitions the same way a sighted user sees them. */}
      <div className="text-center" aria-live="polite" aria-atomic="true">
        <div className="text-base font-medium tracking-tight">
          {labelFor(status)}
        </div>
        <div className="mt-1 text-xs text-muted-foreground">
          {hintFor(status)}
        </div>
      </div>
    </div>
  );
}

function Ring({ tone, delayMs }: { tone: ReturnType<typeof orbTone>; delayMs: number }) {
  return (
    <span
      aria-hidden
      className={cn(
        "absolute inset-0 rounded-full border-2 opacity-0",
        tone.ring,
      )}
      style={{
        animation: "voiceorb-pulse 2.7s ease-out infinite",
        animationDelay: `${delayMs}ms`,
      }}
    />
  );
}

function labelFor(status: OrbStatus): string {
  switch (status) {
    case "idle":       return "Tap to start the conversation";
    case "connecting": return "Connecting…";
    case "listening":  return "I'm listening";
    case "agent":      return "Agent speaking";
    case "ending":     return "Wrapping up…";
    case "error":      return "Something went wrong — tap to retry";
  }
}

function hintFor(status: OrbStatus): string {
  switch (status) {
    case "idle":       return "Speak naturally once it's open. Conversation continues hands-free.";
    case "connecting": return "Establishing a secure session";
    case "listening":  return "Just talk — no need to press anything between turns.";
    case "agent":      return "Speak any time to interrupt.";
    case "ending":     return "Closing the session";
    case "error":      return "If this persists, check the backend log.";
  }
}

function orbTone(status: OrbStatus) {
  switch (status) {
    case "listening":
      return {
        bg: "bg-primary text-primary-foreground",
        border: "border-primary",
        fg: "",
        ring: "border-primary/60",
      };
    case "agent":
      return {
        bg: "bg-emerald-500 text-emerald-50",
        border: "border-emerald-400",
        fg: "",
        ring: "border-emerald-400/70",
      };
    case "error":
      return {
        bg: "bg-destructive text-destructive-foreground",
        border: "border-destructive",
        fg: "",
        ring: "border-destructive/60",
      };
    case "connecting":
    case "ending":
      return {
        bg: "bg-muted text-muted-foreground",
        border: "border-muted",
        fg: "",
        ring: "border-muted",
      };
    case "idle":
    default:
      return {
        bg: "bg-card text-foreground",
        border: "border-border",
        fg: "",
        ring: "border-border",
      };
  }
}

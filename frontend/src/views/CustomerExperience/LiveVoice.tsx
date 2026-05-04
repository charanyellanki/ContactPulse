/**
 * LiveVoice — owns the WebSocket + audio plumbing for the realtime voice
 * channel. The visual is delegated to <VoiceOrb/>; this component only
 * decides what status to surface and what level to show.
 *
 * Continuous conversation: once started, the WebSocket stays open and the
 * mic stays on for the whole session. Each "turn" is a VAD-cut utterance
 * inside that session. The user does not — and should not — tap the orb
 * between turns. The orb's status pill makes that explicit.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  StreamingPlayer,
  arrayBufferToBase64,
  base64ToArrayBuffer,
  startMicCapture,
  type MicCapture,
} from "@/lib/liveAudio";
import { VoiceOrb, type OrbStatus } from "./VoiceOrb";

type Session = "idle" | "connecting" | "live" | "ending" | "error";

export interface LiveTranscriptTurn {
  role: "customer" | "agent";
  text: string;
  timestamp: string;
}

interface Props {
  traceId: string;
  customerId: string | null;
  onTurn: (turn: LiveTranscriptTurn) => void;
  onError?: (message: string) => void;
}

function wsUrlFromApiBase(): string {
  const base =
    (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
    "http://localhost:8000";
  const proto = base.startsWith("https") ? "wss" : "ws";
  const noProto = base.replace(/^https?:\/\//, "");
  return `${proto}://${noProto}/agent/voice/live`;
}

export function LiveVoice({ traceId, customerId, onTurn, onError }: Props) {
  const [session, setSession] = useState<Session>("idle");
  // `agentSpeaking` is timer-decayed: each inbound audio frame keeps it
  // alive; if no audio arrives for ~600 ms we flip back to "listening".
  // Without this, the orb would stay stuck on "agent" forever after the
  // bot finishes naturally (only barge-in clears it otherwise).
  const [agentSpeaking, setAgentSpeaking] = useState(false);
  const [level, setLevel] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const captureRef = useRef<MicCapture | null>(null);
  // Synchronous flag — guards against double-opening the mic when several
  // server frames arrive before `startMicCapture` (which awaits getUserMedia
  // + worklet load — easily 100ms+) resolves and sets `captureRef`.
  const micOpeningRef = useRef(false);
  const playerRef = useRef<StreamingPlayer | null>(null);
  const speakingTimerRef = useRef<number | null>(null);
  const rafRef = useRef<number | null>(null);

  const cleanup = useCallback(async () => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (speakingTimerRef.current !== null) {
      window.clearTimeout(speakingTimerRef.current);
      speakingTimerRef.current = null;
    }
    try { wsRef.current?.close(); } catch { /* ignore */ }
    wsRef.current = null;
    try { await captureRef.current?.stop(); } catch { /* ignore */ }
    captureRef.current = null;
    micOpeningRef.current = false;
    try { await playerRef.current?.close(); } catch { /* ignore */ }
    playerRef.current = null;
    setAgentSpeaking(false);
    setLevel(0);
  }, []);

  useEffect(() => {
    return () => {
      void cleanup();
    };
  }, [cleanup]);

  const bumpAgentSpeaking = useCallback(() => {
    setAgentSpeaking(true);
    if (speakingTimerRef.current !== null) {
      window.clearTimeout(speakingTimerRef.current);
    }
    speakingTimerRef.current = window.setTimeout(() => {
      setAgentSpeaking(false);
      speakingTimerRef.current = null;
    }, 600);
  }, []);

  const handleServerMessage = useCallback(
    (raw: string) => {
      let msg: { type?: string; [k: string]: unknown };
      try {
        msg = JSON.parse(raw);
      } catch {
        return;
      }
      switch (msg.type) {
        case "ready":
          setSession("live");
          break;
        case "audio": {
          const data = typeof msg.data === "string" ? msg.data : "";
          if (!data || !playerRef.current) return;
          playerRef.current.enqueue(base64ToArrayBuffer(data));
          bumpAgentSpeaking();
          break;
        }
        case "user_transcript": {
          const text = String(msg.text ?? "").trim();
          if (text) {
            onTurn({
              role: "customer",
              text,
              timestamp: new Date().toISOString(),
            });
          }
          break;
        }
        case "assistant_text": {
          const text = String(msg.text ?? "").trim();
          if (text) {
            onTurn({
              role: "agent",
              text,
              timestamp: new Date().toISOString(),
            });
          }
          break;
        }
        case "interruption":
          playerRef.current?.flush();
          if (speakingTimerRef.current !== null) {
            window.clearTimeout(speakingTimerRef.current);
            speakingTimerRef.current = null;
          }
          setAgentSpeaking(false);
          break;
        case "error": {
          const m = String(msg.message ?? "live error");
          setSession("error");
          onError?.(m);
          break;
        }
        case "closed":
          setSession("idle");
          break;
        default:
          break;
      }
    },
    [bumpAgentSpeaking, onError, onTurn],
  );

  // Audio-level loop. We drive the VoiceOrb from whichever side currently
  // has the floor — playback while the agent talks, mic otherwise.
  const startLevelLoop = useCallback(() => {
    const tick = () => {
      const cap = captureRef.current;
      const ply = playerRef.current;
      let next = 0;
      if (ply && (ply.isPlaying() || agentSpeakingRef.current)) {
        next = ply.getLevel();
      } else if (cap) {
        next = cap.getLevel();
      }
      setLevel(next);
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, []);

  // Keep a ref synced with `agentSpeaking` so the rAF tick (which captures
  // closures once) reads fresh state without re-subscribing each frame.
  const agentSpeakingRef = useRef(false);
  useEffect(() => {
    agentSpeakingRef.current = agentSpeaking;
  }, [agentSpeaking]);

  const start = useCallback(async () => {
    if (session === "live" || session === "connecting") return;
    setSession("connecting");
    setAgentSpeaking(false);

    const player = new StreamingPlayer();
    await player.resume();
    playerRef.current = player;

    let ws: WebSocket;
    try {
      ws = new WebSocket(wsUrlFromApiBase());
    } catch (err) {
      const message = err instanceof Error ? err.message : "websocket failed";
      onError?.(message);
      setSession("error");
      await cleanup();
      return;
    }
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(
        JSON.stringify({
          type: "hello",
          trace_id: traceId,
          customer_id: customerId,
        }),
      );
    };

    ws.onmessage = (e) => {
      handleServerMessage(typeof e.data === "string" ? e.data : "");
      // Open mic on first server frame, but only once. The synchronous
      // `micOpeningRef` guard prevents a double-open when several frames
      // arrive before `startMicCapture` resolves.
      if (!captureRef.current && !micOpeningRef.current) {
        micOpeningRef.current = true;
        void openMic(ws);
      }
    };

    ws.onerror = () => {
      onError?.("websocket error");
      setSession("error");
      void cleanup();
    };

    ws.onclose = () => {
      setSession((prev) => (prev === "ending" ? "idle" : prev));
      void cleanup();
    };

    const openMic = async (socket: WebSocket) => {
      try {
        const capture = await startMicCapture({
          onFrame: (pcm) => {
            if (socket.readyState !== WebSocket.OPEN) return;
            socket.send(
              JSON.stringify({
                type: "audio",
                data: arrayBufferToBase64(pcm),
              }),
            );
          },
          onError: (m) => onError?.(m),
        });
        captureRef.current = capture;
        startLevelLoop();
      } catch (err) {
        const m = err instanceof Error ? err.message : "mic failed";
        onError?.(m);
        setSession("error");
        await cleanup();
      } finally {
        micOpeningRef.current = false;
      }
    };
  }, [cleanup, customerId, handleServerMessage, onError, session, startLevelLoop, traceId]);

  const stop = useCallback(async () => {
    if (session === "idle") return;
    setSession("ending");
    try {
      wsRef.current?.send(JSON.stringify({ type: "close" }));
    } catch {
      /* ignore */
    }
    await cleanup();
    setSession("idle");
  }, [cleanup, session]);

  const orbStatus: OrbStatus = orbStatusFor(session, agentSpeaking);

  return (
    <VoiceOrb
      status={orbStatus}
      level={level}
      onStart={start}
      onStop={stop}
    />
  );
}

function orbStatusFor(session: Session, agentSpeaking: boolean): OrbStatus {
  if (session === "live") return agentSpeaking ? "agent" : "listening";
  return session;
}

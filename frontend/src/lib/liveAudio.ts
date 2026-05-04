/**
 * Browser-side helpers for the live voice mode (CLAUDE.md §14).
 *
 * Three responsibilities:
 *   1. CAPTURE: pipe the mic into an AudioWorklet that emits 16 kHz 16-bit
 *      mono PCM frames. Each frame is delivered to a callback.
 *   2. PLAYBACK: decode incoming PCM 24 kHz chunks from Gemini Live, schedule
 *      them on a single AudioContext timeline so they play seamlessly, and
 *      support `flush()` for barge-in.
 *   3. LEVELS: both capture and playback expose `getLevel()` returning a
 *      smoothed RMS value in [0, 1] — used to drive the VoiceOrb pulse.
 *
 * Why AudioWorklet (not ScriptProcessorNode): per CLAUDE.md §14, ScriptProcessor
 * is deprecated and runs on the main thread, which adds jitter that kills the
 * conversational feel. The worklet runs on the audio thread.
 */

const RECORDER_WORKLET_URL = "/audio/recorder-worklet.js";

// Gemini Live audio formats (stable as of 2026-05).
export const LIVE_INPUT_SAMPLE_RATE = 16000;
export const LIVE_OUTPUT_SAMPLE_RATE = 24000;


function readLevel(
  analyser: AnalyserNode,
  scratch: Uint8Array<ArrayBuffer>,
): number {
  // Time-domain RMS — cheaper than fft and gives a more natural meter than
  // frequency-domain peaks.
  analyser.getByteTimeDomainData(scratch);
  let sumSq = 0;
  for (let i = 0; i < scratch.length; i++) {
    const v = (scratch[i] - 128) / 128;
    sumSq += v * v;
  }
  const rms = Math.sqrt(sumSq / scratch.length);
  // Compress quiet → moderate range so the orb actually moves on normal
  // speech (typical RMS is 0.02–0.15).
  return Math.min(1, rms * 4);
}


// ─── Capture ──────────────────────────────────────────────────────────────


export interface MicCapture {
  /** Stop the mic, tear down the worklet, close the capture context. */
  stop: () => Promise<void>;
  /** Smoothed mic input level in [0, 1]. */
  getLevel: () => number;
}

export interface MicCaptureOptions {
  onFrame: (pcm: ArrayBuffer) => void;
  onError?: (message: string) => void;
}

/** Open the microphone, attach the recorder worklet, deliver PCM frames. */
export async function startMicCapture(opts: MicCaptureOptions): Promise<MicCapture> {
  let stream: MediaStream | null = null;
  let ctx: AudioContext | null = null;
  let source: MediaStreamAudioSourceNode | null = null;
  let node: AudioWorkletNode | null = null;
  let analyser: AnalyserNode | null = null;

  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      },
    });
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "could not access microphone";
    opts.onError?.(message);
    throw new Error(message);
  }

  const Ctor: typeof AudioContext =
    window.AudioContext ||
    (window as unknown as { webkitAudioContext: typeof AudioContext })
      .webkitAudioContext;
  ctx = new Ctor({ sampleRate: LIVE_INPUT_SAMPLE_RATE, latencyHint: "interactive" });

  try {
    await ctx.audioWorklet.addModule(RECORDER_WORKLET_URL);
  } catch (err) {
    const message =
      err instanceof Error
        ? `audio worklet load failed: ${err.message}`
        : "audio worklet load failed";
    opts.onError?.(message);
    stream.getTracks().forEach((t) => t.stop());
    await ctx.close();
    throw new Error(message);
  }

  source = ctx.createMediaStreamSource(stream);
  node = new AudioWorkletNode(ctx, "recorder-processor", {
    numberOfInputs: 1,
    numberOfOutputs: 0,
    channelCount: 1,
    processorOptions: { frameSamples: 1600 }, // 100 ms @ 16 kHz
  });
  node.port.onmessage = (e) => {
    if (e.data instanceof ArrayBuffer) opts.onFrame(e.data);
  };

  analyser = ctx.createAnalyser();
  analyser.fftSize = 1024;
  analyser.smoothingTimeConstant = 0.6;
  const scratch = new Uint8Array(new ArrayBuffer(analyser.fftSize));

  source.connect(node);
  source.connect(analyser);

  // Smoothing — readLevel is cheap so we can poll it on every getLevel call.
  let smoothed = 0;
  const getLevel = (): number => {
    if (!analyser) return 0;
    const raw = readLevel(analyser, scratch);
    smoothed = smoothed * 0.6 + raw * 0.4;
    return smoothed;
  };

  return {
    getLevel,
    stop: async () => {
      try { node?.port.close(); } catch { /* ignore */ }
      try { node?.disconnect(); } catch { /* ignore */ }
      try { analyser?.disconnect(); } catch { /* ignore */ }
      try { source?.disconnect(); } catch { /* ignore */ }
      stream?.getTracks().forEach((t) => t.stop());
      try { await ctx?.close(); } catch { /* ignore */ }
    },
  };
}

// ─── Playback ─────────────────────────────────────────────────────────────


/**
 * Streaming PCM playback. Schedules each chunk on the AudioContext timeline
 * so consecutive chunks abut without gaps.
 *
 * Barge-in (`flush`) cancels every chunk scheduled past `currentTime` and
 * resets the cursor — the bot stops speaking *now*, not at the next chunk
 * boundary.
 */
export class StreamingPlayer {
  private ctx: AudioContext;
  private cursor: number;
  private active: Set<AudioBufferSourceNode> = new Set();
  private analyser: AnalyserNode;
  private scratch: Uint8Array<ArrayBuffer>;
  private smoothed = 0;
  private readonly sampleRate: number;

  constructor(sampleRate = LIVE_OUTPUT_SAMPLE_RATE) {
    const Ctor: typeof AudioContext =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext })
        .webkitAudioContext;
    this.ctx = new Ctor({ sampleRate });
    this.sampleRate = sampleRate;
    this.cursor = this.ctx.currentTime;
    this.analyser = this.ctx.createAnalyser();
    this.analyser.fftSize = 1024;
    this.analyser.smoothingTimeConstant = 0.6;
    this.analyser.connect(this.ctx.destination);
    this.scratch = new Uint8Array(new ArrayBuffer(this.analyser.fftSize));
  }

  /** Resume the AudioContext if it's suspended (autoplay-policy guard). */
  async resume(): Promise<void> {
    if (this.ctx.state === "suspended") {
      await this.ctx.resume();
    }
    if (this.cursor < this.ctx.currentTime) this.cursor = this.ctx.currentTime;
  }

  /** Schedule a PCM chunk (16-bit signed little-endian) for playback. */
  enqueue(pcm: ArrayBuffer): void {
    const samples = new Int16Array(pcm);
    if (samples.length === 0) return;
    const buf = this.ctx.createBuffer(1, samples.length, this.sampleRate);
    const channel = buf.getChannelData(0);
    for (let i = 0; i < samples.length; i++) {
      channel[i] = samples[i] / 0x8000;
    }
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    // Route through the analyser → destination so getLevel() sees the audio
    // we're actually outputting.
    src.connect(this.analyser);
    if (this.cursor < this.ctx.currentTime) this.cursor = this.ctx.currentTime;
    src.start(this.cursor);
    this.cursor += buf.duration;
    this.active.add(src);
    src.onended = () => this.active.delete(src);
  }

  /** Smoothed playback level in [0, 1]. */
  getLevel(): number {
    if (this.active.size === 0 && this.cursor <= this.ctx.currentTime) {
      // Decay quickly toward zero when silent — visually clearer than letting
      // the analyser's smoothing drag the meter down on its own.
      this.smoothed *= 0.7;
      return this.smoothed;
    }
    const raw = readLevel(this.analyser, this.scratch);
    this.smoothed = this.smoothed * 0.6 + raw * 0.4;
    return this.smoothed;
  }

  /** True iff there is audio scheduled at or after `currentTime`. */
  isPlaying(): boolean {
    return this.active.size > 0 || this.cursor > this.ctx.currentTime + 0.02;
  }

  /** Stop everything currently scheduled. Used for barge-in. */
  flush(): void {
    for (const s of this.active) {
      try { s.stop(); } catch { /* already stopped */ }
    }
    this.active.clear();
    this.cursor = this.ctx.currentTime;
  }

  async close(): Promise<void> {
    this.flush();
    this.active.clear();
    try { this.analyser.disconnect(); } catch { /* ignore */ }
    try { await this.ctx.close(); } catch { /* ignore */ }
  }
}

// ─── Encoding helpers ─────────────────────────────────────────────────────


export function arrayBufferToBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let s = "";
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.byteLength; i += CHUNK) {
    s += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(s);
}

export function base64ToArrayBuffer(b64: string): ArrayBuffer {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes.buffer;
}

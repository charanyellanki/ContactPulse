/**
 * AudioWorklet processor: capture mic audio and emit fixed-size 16-bit PCM
 * frames over postMessage. Used by the live voice mode (CLAUDE.md §14).
 *
 * The hosting AudioContext is created with sampleRate=16000 so the input
 * stream is resampled to 16 kHz before it reaches us — the buffer we emit
 * is therefore already at the rate Gemini Live expects.
 *
 * Frame size defaults to 1600 samples (= 100 ms @ 16 kHz) which keeps
 * end-to-end latency low while batching enough audio to amortize WebSocket
 * frame overhead.
 */
class RecorderProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const frameSamples = options?.processorOptions?.frameSamples ?? 1600;
    this._frameSize = frameSamples;
    this._buf = new Int16Array(this._frameSize);
    this._pos = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const ch = input[0];
    if (!ch) return true;
    for (let i = 0; i < ch.length; i++) {
      const s = Math.max(-1, Math.min(1, ch[i]));
      this._buf[this._pos++] = s < 0 ? s * 0x8000 : s * 0x7fff;
      if (this._pos === this._frameSize) {
        // Slice into a fresh ArrayBuffer so the transferable doesn't alias
        // our internal buffer.
        const out = this._buf.slice(0).buffer;
        this.port.postMessage(out, [out]);
        this._pos = 0;
      }
    }
    return true;
  }
}

registerProcessor("recorder-processor", RecorderProcessor);

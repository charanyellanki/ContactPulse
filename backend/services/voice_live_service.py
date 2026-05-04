"""Gemini Live API session manager for the realtime voice channel.

CLAUDE.md §14: this is the only place that talks to Gemini Live. Routes own
the WebSocket; this service owns the Live session, the tool registry, and
trace emission. Tools wrap existing repositories — no new business logic.

Architecture (per ARCHITECTURE.md §4.3):

    browser PCM 16k ─► WS  ─►  voice_live_service.LiveSession
                                  │  audio_in (Blob 16k)
                                  ▼
                              Vertex AI Gemini Live (BidiGenerateContent)
                                  │  audio_out (24k), transcripts, tool calls
                                  ▼
                              voice_live_service.LiveSession
                                  │  trace events (live_*) → BigQuery
                                  │  tool calls → repositories
                                  ▼
                              browser PCM 24k

The session is bound to one WebSocket and one trace_id. When the WebSocket
closes, the Gemini Live session is torn down and the conversation summary
row is written.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.config import get_settings
from backend.repositories.bigquery_client import get_bq_client
from backend.repositories.order_repo import OrderRepository
from backend.repositories.trace_writer import TraceWriter
from backend.services.dlp_service import get_dlp_service

log = logging.getLogger(__name__)


# ─── Public types ────────────────────────────────────────────────────────────


@dataclass
class LiveOutboundAudio:
    """One chunk of PCM audio ready for the browser. 24 kHz 16-bit mono."""

    pcm_bytes: bytes


@dataclass
class LiveOutboundEvent:
    """A non-audio event for the browser (status, transcript, error)."""

    type: str  # "ready" | "user_transcript" | "assistant_text" | "interruption" | "error" | "closed"
    payload: dict[str, Any] = field(default_factory=dict)


LiveOutbound = LiveOutboundAudio | LiveOutboundEvent


# ─── Tool registry ───────────────────────────────────────────────────────────
#
# Tools are typed wrappers over existing repositories. Each entry has:
#   - declaration: what Gemini sees (name, description, parameters JSON-schema)
#   - handler:     async callable executing it server-side
#
# Adding a tool: write the wrapper, append a declaration + handler entry, and
# update the system prompt in `prompts/voice_live_system.txt`. CLAUDE.md §14.


_LOOKUP_RECENT_ORDERS = {
    "name": "lookup_recent_orders",
    "description": (
        "Look up the most recent orders for a known customer. Use when the "
        "caller is logged in and asks about their orders without citing a "
        "specific order number. Requires `customer_id` (provided at session "
        "start in the system context)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "customer_id": {
                "type": "string",
                "description": "Synthetic customer ID provided at session start.",
            }
        },
        "required": ["customer_id"],
    },
}


_LOOKUP_ORDER_BY_ID = {
    "name": "lookup_order_by_id",
    "description": (
        "Look up a single order by its ID. Use when the caller cites an order "
        "number (e.g. '1042', '#4521')."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "string",
                "description": (
                    "Order ID as the caller stated it. May or may not include "
                    "the leading '#'."
                ),
            }
        },
        "required": ["order_id"],
    },
}


_SEARCH_KB = {
    "name": "search_knowledge_base",
    "description": (
        "Search the product and policy knowledge base. Use for any warranty, "
        "return-policy, product-spec, or installation question. Returns "
        "ranked passages with sources."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The customer's question, paraphrased.",
            }
        },
        "required": ["query"],
    },
}


_BOOK_SERVICE_REQUEST = {
    "name": "book_service_request",
    "description": (
        "Submit a service-request booking once you've collected service_type, "
        "preferred_date, and address. Returns a synthetic confirmation ID."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "service_type": {
                "type": "string",
                "enum": ["installation", "repair", "consultation"],
            },
            "preferred_date": {
                "type": "string",
                "description": "Customer's preferred date or window in their words.",
            },
            "address": {
                "type": "string",
                "description": "Visit address.",
            },
        },
        "required": ["service_type", "preferred_date", "address"],
    },
}


_ESCALATE = {
    "name": "escalate_to_human",
    "description": (
        "Hand off to a human associate. Use when the customer asks, when the "
        "topic is out of scope, or when you are not confident. Once called, "
        "wrap up briefly — do not continue trying to help."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": (
                    "Short reason for the handoff (e.g. 'customer requested', "
                    "'out of scope', 'low confidence after retries')."
                ),
            }
        },
        "required": ["reason"],
    },
}


_TOOL_DECLARATIONS: list[dict[str, Any]] = [
    _LOOKUP_RECENT_ORDERS,
    _LOOKUP_ORDER_BY_ID,
    _SEARCH_KB,
    _BOOK_SERVICE_REQUEST,
    _ESCALATE,
]


# Hardcoded KB stub mirrors product_qa_agent's three passages so Live mode and
# push-to-talk mode return the same KB shape. When `retrieval/` lands, swap
# this for the real hybrid_search call.
_KB_STUB: list[dict[str, Any]] = [
    {
        "source": "return_policy.pdf",
        "passage": (
            "Return policy: most products may be returned within 90 days with the "
            "original receipt. Opened paint can be returned within 30 days for "
            "store credit only. Major appliances must be returned within 48 hours "
            "of delivery. Online orders can be returned in-store or by mail."
        ),
    },
    {
        "source": "product_guide.pdf",
        "passage": (
            "Cordless Drill X-200: 20V brushless motor, 2.0Ah lithium-ion battery, "
            "1/2-inch chuck, 3-year limited warranty covering defects in materials "
            "and workmanship. Battery and charger sold with the kit. LED work light. "
            "Compatible with all 20V Max system batteries."
        ),
    },
    {
        "source": "warranty.pdf",
        "passage": (
            "Standard manufacturer warranty terms: power tools carry a 3-year limited "
            "warranty; outdoor power equipment carries 2 years; major appliances "
            "carry 1 year on parts and labor. Extended protection plans add 2-5 years "
            "and must be purchased within 30 days of the original sale."
        ),
    },
]


# ─── Session state ───────────────────────────────────────────────────────────


@dataclass
class _SessionContext:
    trace_id: str
    customer_id: str | None
    started_at: float
    turn_count: int = 0
    interrupted_pending: bool = False
    escalated: bool = False
    pending_assistant_text: list[str] = field(default_factory=list)
    pending_user_text: list[str] = field(default_factory=list)


# ─── Prompt loader ───────────────────────────────────────────────────────────

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


@lru_cache(maxsize=1)
def _load_system_instruction() -> str:
    return (_PROMPT_DIR / "voice_live_system.txt").read_text(encoding="utf-8")


# ─── Lazy genai client ───────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _genai_client():  # type: ignore[no-untyped-def]
    """Vertex-mode google-genai client. Lazy so import-time doesn't require
    Vertex creds in test environments that never open a Live session."""
    from google import genai

    s = get_settings()
    return genai.Client(
        vertexai=True,
        project=s.project_id,
        location=s.gemini_live_region,
    )


# ─── Tool execution ──────────────────────────────────────────────────────────


@dataclass
class _ToolResult:
    payload: dict[str, Any]
    latency_ms: int
    preview: str


async def _exec_tool(name: str, args: dict[str, Any], ctx: _SessionContext) -> _ToolResult:
    """Run one tool call. All side effects go through existing repositories."""
    started = time.perf_counter()
    payload: dict[str, Any]
    preview: str

    if name == "lookup_recent_orders":
        cust = args.get("customer_id") or ctx.customer_id
        if not cust:
            payload = {"error": "no customer_id available — caller is anonymous"}
            preview = "anonymous"
        else:
            repo = OrderRepository(get_bq_client())
            orders = await asyncio.to_thread(repo.recent_orders_for_customer, cust)
            payload = {
                "orders": [
                    {
                        "order_id":     o.order_id,
                        "product_name": o.product_name,
                        "status":       o.status,
                        "order_date":   o.order_date,
                        "eta":          o.eta,
                    }
                    for o in orders
                ],
                "count": len(orders),
            }
            preview = f"{len(orders)} orders"

    elif name == "lookup_order_by_id":
        raw = str(args.get("order_id", "")).strip()
        order_id = raw if raw.startswith("#") else (f"#{raw}" if raw.isdigit() else raw)
        repo = OrderRepository(get_bq_client())
        order = await asyncio.to_thread(repo.get_order, order_id)
        if order is None:
            payload = {"found": False, "order_id": order_id}
            preview = f"{order_id} not found"
        else:
            payload = {
                "found":        True,
                "order_id":     order.order_id,
                "product_name": order.product_name,
                "status":       order.status,
                "order_date":   order.order_date,
                "eta":          order.eta,
                "tracking_no":  order.tracking_no,
                "belongs_to":   order.customer_id,
            }
            preview = f"{order.order_id} {order.status}"

    elif name == "search_knowledge_base":
        query = str(args.get("query", "")).strip()
        # KB stub — same three passages as product_qa_agent. Replace with
        # `retrieval/` when Vertex AI Search lands.
        payload = {
            "passages": [
                {"source": p["source"], "passage": p["passage"]}
                for p in _KB_STUB
            ],
            "query": query,
        }
        preview = f"3 passages for {query[:40]!r}"

    elif name == "book_service_request":
        # Synthetic — mirrors the slot-filling agent's behavior: capture and
        # echo back without actually writing anywhere.
        payload = {
            "confirmation_id": f"SR-{int(time.time()) % 1_000_000:06d}",
            "service_type":    args.get("service_type"),
            "preferred_date":  args.get("preferred_date"),
            "address":         args.get("address"),
            "status":          "received",
        }
        preview = f"booked {args.get('service_type')}"

    elif name == "escalate_to_human":
        ctx.escalated = True
        payload = {
            "transferred": True,
            "reason":      args.get("reason", "unspecified"),
        }
        preview = f"escalate: {args.get('reason', 'unspecified')[:40]}"

    else:
        payload = {"error": f"unknown tool: {name}"}
        preview = f"unknown:{name}"

    latency_ms = int((time.perf_counter() - started) * 1000)
    return _ToolResult(payload=payload, latency_ms=latency_ms, preview=preview)


# ─── Trace emission ──────────────────────────────────────────────────────────


def _trace_writer() -> TraceWriter:
    return TraceWriter(get_bq_client())


async def _write_trace_async(**kwargs: Any) -> None:
    """BigQuery streaming insert is a blocking IO call — push it to a thread
    so it does not block the audio forwarding tasks."""
    tw = _trace_writer()
    await asyncio.to_thread(tw.write_event, **kwargs)


async def _write_summary_async(**kwargs: Any) -> None:
    tw = _trace_writer()
    await asyncio.to_thread(tw.write_conversation_summary, **kwargs)


# ─── The session itself ──────────────────────────────────────────────────────


class LiveSession:
    """One Gemini Live session, bound to one WebSocket and one trace ID.

    The session exposes two queues to the route:
      - `inbound`:  audio + control messages from the browser.
      - `outbound`: audio + status events to the browser.

    The session runs a background pump task that:
      1. Opens the Vertex Live `connect` context.
      2. Spawns a forwarder for browser-→Live audio.
      3. Loops over Live's response stream, emitting audio + transcripts +
         executing tool calls.
      4. Tears everything down on close.
    """

    def __init__(self, *, trace_id: str, customer_id: str | None) -> None:
        self.trace_id = trace_id
        self.customer_id = customer_id
        self._ctx = _SessionContext(
            trace_id=trace_id,
            customer_id=customer_id,
            started_at=time.perf_counter(),
        )

        self.inbound: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self.outbound: asyncio.Queue[LiveOutbound | None] = asyncio.Queue()

        self._closed = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name=f"live-session-{self.trace_id}")

    async def stop(self) -> None:
        """Caller-facing shutdown. Drains tasks, writes the close trace event."""
        if self._closed.is_set():
            return
        self._closed.set()
        # Sentinel for the inbound forwarder to exit cleanly.
        await self.inbound.put(None)
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except asyncio.TimeoutError:
                self._task.cancel()
            except Exception:
                log.exception("live session task failed during stop trace=%s", self.trace_id)

    async def _emit(self, item: LiveOutbound) -> None:
        await self.outbound.put(item)

    async def _emit_event(self, type_: str, **payload: Any) -> None:
        await self._emit(LiveOutboundEvent(type=type_, payload=payload))

    async def _run(self) -> None:
        s = get_settings()
        try:
            from google.genai import types as gt
        except Exception:                              # noqa: BLE001
            log.exception("google-genai not available — install requirements.txt")
            await self._emit_event("error", message="live mode unavailable on server")
            await self.outbound.put(None)
            return

        # Greet the browser before we even open the upstream — avoids the
        # 'is anything happening?' window if Vertex is slow to handshake.
        await self._emit_event("ready", trace_id=self.trace_id)

        # Build the LiveConnectConfig.
        # `response_modalities=["AUDIO"]` asks Gemini to speak (not type) —
        # we still get transcripts via the *_audio_transcription fields.
        try:
            config = gt.LiveConnectConfig(
                response_modalities=["AUDIO"],
                speech_config=gt.SpeechConfig(
                    voice_config=gt.VoiceConfig(
                        prebuilt_voice_config=gt.PrebuiltVoiceConfig(
                            voice_name=s.gemini_live_voice,
                        )
                    ),
                    language_code=s.gemini_live_language,
                ),
                system_instruction=gt.Content(
                    parts=[gt.Part(text=self._system_instruction())]
                ),
                tools=[gt.Tool(function_declarations=_TOOL_DECLARATIONS)],
                input_audio_transcription=gt.AudioTranscriptionConfig(),
                output_audio_transcription=gt.AudioTranscriptionConfig(),
            )
        except Exception:                              # noqa: BLE001
            # Don't surface raw exception strings — Vertex errors typically
            # include project IDs, regions, and model paths.
            log.exception("live config build failed")
            await self._emit_event("error", message="live mode unavailable on server")
            await self.outbound.put(None)
            return

        # Trace: session opened.
        await _write_trace_async(
            trace_id=self.trace_id,
            event_type="live_session_open",
            latency_ms=0,
            metadata={
                "model":       s.gemini_live_model,
                "voice":       s.gemini_live_voice,
                "language":    s.gemini_live_language,
                "customer_id": self.customer_id,
            },
        )

        client = _genai_client()

        try:
            async with client.aio.live.connect(
                model=s.gemini_live_model, config=config
            ) as session:
                # Two cooperative tasks: pump audio up, pump audio + events down.
                up = asyncio.create_task(
                    self._pump_inbound(session), name="live-up"
                )
                down = asyncio.create_task(
                    self._pump_outbound(session), name="live-down"
                )

                # Soft session timeout — bound the cost surface.
                deadline = self._ctx.started_at + s.gemini_live_session_max_seconds

                while not self._closed.is_set():
                    if time.perf_counter() > deadline:
                        await self._emit_event(
                            "error",
                            message="session time limit reached — please reconnect",
                        )
                        break
                    if up.done() or down.done():
                        break
                    await asyncio.sleep(0.25)

                for t in (up, down):
                    if not t.done():
                        t.cancel()
                # Surface task exceptions in logs (not to the browser).
                for t in (up, down):
                    try:
                        await t
                    except (asyncio.CancelledError, Exception):
                        pass
        except Exception:                              # noqa: BLE001
            # Generic message to the browser; full detail stays in logs.
            log.exception("live session crashed trace=%s", self.trace_id)
            await self._emit_event(
                "error", message="live session ended unexpectedly"
            )
        finally:
            await self._close()

    def _system_instruction(self) -> str:
        base = _load_system_instruction()
        if self.customer_id:
            return (
                base
                + f"\n\nSESSION CONTEXT:\n- customer_id: {self.customer_id}\n"
                "- The caller is logged in. You may pass this customer_id to "
                "lookup_recent_orders without asking for it."
            )
        return (
            base
            + "\n\nSESSION CONTEXT:\n- The caller is anonymous. If they ask "
            "about an order, ask for the order number first."
        )

    async def _pump_inbound(self, session: Any) -> None:
        """Forward browser audio chunks into the Live session."""
        from google.genai import types as gt

        while not self._closed.is_set():
            msg = await self.inbound.get()
            if msg is None:
                break
            mtype = msg.get("type")
            if mtype == "audio":
                pcm = msg.get("pcm")
                if not pcm:
                    continue
                try:
                    await session.send_realtime_input(
                        media=gt.Blob(data=pcm, mime_type="audio/pcm;rate=16000")
                    )
                except Exception:                      # noqa: BLE001
                    log.exception("inbound audio send failed")
                    break
            elif mtype == "end_audio":
                # Browser explicitly signalled end-of-stream (e.g. user
                # clicked stop). Live closes its turn naturally on VAD,
                # but we forward this hint when present.
                try:
                    await session.send_realtime_input(audio_stream_end=True)
                except Exception:                      # noqa: BLE001
                    log.debug("audio_stream_end not supported on this SDK version", exc_info=True)
            else:
                log.debug("unhandled inbound msg type=%s", mtype)

    async def _pump_outbound(self, session: Any) -> None:
        """Pull responses off the Live session: audio, transcripts, tool calls."""
        try:
            async for response in session.receive():
                await self._handle_response(session, response)
        except asyncio.CancelledError:
            raise
        except Exception:                              # noqa: BLE001
            log.exception("outbound pump crashed trace=%s", self.trace_id)

    async def _handle_response(self, session: Any, response: Any) -> None:
        """Decode one response from the Live stream and emit derived events."""

        # 1) Audio out — push raw PCM 24k to the browser.
        data = getattr(response, "data", None)
        if data:
            await self._emit(LiveOutboundAudio(pcm_bytes=data))

        # 2) Server content — transcripts, turn boundaries, interruptions.
        sc = getattr(response, "server_content", None)
        if sc is not None:
            await self._handle_server_content(sc)

        # 3) Tool calls — execute and respond.
        tc = getattr(response, "tool_call", None)
        if tc is not None:
            await self._handle_tool_call(session, tc)

    async def _handle_server_content(self, sc: Any) -> None:
        # User-side transcript (after VAD cuts a turn).
        in_t = getattr(sc, "input_transcription", None)
        if in_t is not None:
            text = getattr(in_t, "text", "") or ""
            if text:
                self._ctx.pending_user_text.append(text)

        out_t = getattr(sc, "output_transcription", None)
        if out_t is not None:
            text = getattr(out_t, "text", "") or ""
            if text:
                self._ctx.pending_assistant_text.append(text)

        # Live signals barge-in by setting `interrupted` on the server content.
        if getattr(sc, "interrupted", False):
            cancelled = "".join(self._ctx.pending_assistant_text).strip()
            self._ctx.pending_assistant_text.clear()
            await self._emit_event("interruption")
            await _write_trace_async(
                trace_id=self.trace_id,
                event_type="live_interruption",
                latency_ms=0,
                metadata={"cancelled_text_preview": cancelled[:200]},
                output_text=cancelled or None,
            )

        # End-of-turn — flush both transcripts as one trace row each.
        if getattr(sc, "turn_complete", False):
            user_text = "".join(self._ctx.pending_user_text).strip()
            assistant_text = "".join(self._ctx.pending_assistant_text).strip()
            self._ctx.pending_user_text.clear()
            self._ctx.pending_assistant_text.clear()

            if user_text:
                self._ctx.turn_count += 1
                # DLP runs over the user transcript exactly like batch mode.
                deid = await asyncio.to_thread(
                    get_dlp_service().deidentify, user_text
                )
                await self._emit_event(
                    "user_transcript",
                    text=deid.text,
                    turn=self._ctx.turn_count,
                )
                await _write_trace_async(
                    trace_id=self.trace_id,
                    event_type="live_user_transcript",
                    latency_ms=0,
                    metadata={
                        "turn":             self._ctx.turn_count,
                        "redaction_method": deid.method,
                    },
                    input_text=deid.text,
                    pii_redacted=deid.redacted,
                )

            if assistant_text:
                await self._emit_event(
                    "assistant_text",
                    text=assistant_text,
                    turn=self._ctx.turn_count,
                )
                await _write_trace_async(
                    trace_id=self.trace_id,
                    event_type="live_assistant_text",
                    latency_ms=0,
                    metadata={"turn": self._ctx.turn_count},
                    output_text=assistant_text,
                )

    async def _handle_tool_call(self, session: Any, tool_call: Any) -> None:
        from google.genai import types as gt

        function_calls = getattr(tool_call, "function_calls", None) or []
        responses: list[Any] = []
        for fc in function_calls:
            name = getattr(fc, "name", "") or ""
            args = dict(getattr(fc, "args", {}) or {})
            call_id = getattr(fc, "id", None)

            try:
                result = await _exec_tool(name, args, self._ctx)
                payload = result.payload
                preview = result.preview
                latency = result.latency_ms
            except Exception as exc:                   # noqa: BLE001
                log.exception("tool %s failed", name)
                payload = {"error": str(exc)}
                preview = f"error: {exc}"
                latency = 0

            await _write_trace_async(
                trace_id=self.trace_id,
                event_type="live_tool_call",
                latency_ms=latency,
                metadata={
                    "tool_name":      name,
                    "args":           args,
                    "result_preview": preview,
                },
            )

            responses.append(
                gt.FunctionResponse(
                    id=call_id,
                    name=name,
                    response=payload,
                )
            )

        if responses:
            try:
                await session.send_tool_response(function_responses=responses)
            except Exception:                          # noqa: BLE001
                log.exception("tool response send failed trace=%s", self.trace_id)

    async def _close(self) -> None:
        duration_ms = int((time.perf_counter() - self._ctx.started_at) * 1000)
        outcome = "escalated" if self._ctx.escalated else "contained"
        try:
            await _write_trace_async(
                trace_id=self.trace_id,
                event_type="live_session_close",
                latency_ms=duration_ms,
                metadata={
                    "duration_ms": duration_ms,
                    "turn_count":  self._ctx.turn_count,
                    "escalated":   self._ctx.escalated,
                    "channel":     "voice_live",
                },
            )
            # Write `modality="voice"` (not "voice_live") so the row matches
            # the strict `Modality = Literal["voice","chat"]` contract used by
            # both the BigQuery → Pydantic mapping in conversation_repo and
            # the zod schema in the frontend. The "live" distinction is kept
            # in `live_session_close.metadata.channel` for analytics.
            await _write_summary_async(
                trace_id=self.trace_id,
                modality="voice",
                customer_id=self.customer_id,
                tier=None,
                journey=None,
                outcome=outcome,
                turns=self._ctx.turn_count or 1,
                latency_p50_ms=duration_ms,
                cost_usd=0.0,  # Live cost telemetry deferred — see CLAUDE.md §14
            )
        finally:
            await self._emit_event("closed", duration_ms=duration_ms)
            await self.outbound.put(None)


# ─── Public factory ──────────────────────────────────────────────────────────


def new_session(*, trace_id: str, customer_id: str | None) -> LiveSession:
    """Construct a LiveSession. Callers must `await session.start()` and
    then drain `session.outbound`; push browser messages onto `session.inbound`."""
    return LiveSession(trace_id=trace_id, customer_id=customer_id)


def tool_declarations() -> list[dict[str, Any]]:
    """Exposed for tests + `/health` introspection."""
    return list(_TOOL_DECLARATIONS)

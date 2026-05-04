"""Realtime voice WebSocket route — `/agent/voice/live`.

Browser ↔ this WebSocket ↔ Gemini Live (Vertex AI). The route owns the
WebSocket; voice_live_service owns the Live session, tool registry, and
trace emission. CLAUDE.md §14.

Wire format (JSON text frames in both directions, audio as base64):

  client → server
    { "type": "hello",       "trace_id": "...", "customer_id": "..." | null }
    { "type": "audio",       "data": "<base64 PCM 16k mono>" }
    { "type": "end_audio" }                             // optional explicit EOU
    { "type": "close" }                                 // request graceful close

  server → client
    { "type": "ready",                  trace_id }
    { "type": "audio",                  data: "<base64 PCM 24k mono>" }
    { "type": "user_transcript",        text, turn }
    { "type": "assistant_text",         text, turn }
    { "type": "interruption" }
    { "type": "error",                  message }
    { "type": "closed",                 duration_ms }

Audio framing is intentionally simple: discrete JSON frames are easier to
debug in the demo than a binary protocol. Each PCM chunk is ~100 ms; at
16 kHz/16-bit/mono that's ~3.2 KB per frame plus base64 overhead — fine
over WebSocket.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.services import voice_live_service
from backend.services.voice_live_service import (
    LiveOutboundAudio,
    LiveOutboundEvent,
    LiveSession,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])


@router.websocket("/voice/live")
async def voice_live(ws: WebSocket) -> None:
    await ws.accept()

    # Wait for the hello frame to allocate a session. We don't open the
    # upstream Live connection until we know the trace_id and customer_id —
    # otherwise we'd burn a Live session every time a browser opens devtools.
    try:
        first = await asyncio.wait_for(ws.receive_text(), timeout=5.0)
    except (asyncio.TimeoutError, WebSocketDisconnect):
        await ws.close(code=4000, reason="no hello received")
        return

    try:
        hello = json.loads(first)
    except json.JSONDecodeError:
        await ws.close(code=4001, reason="hello must be JSON")
        return

    if hello.get("type") != "hello":
        await ws.close(code=4002, reason="first frame must be hello")
        return

    trace_id = str(hello.get("trace_id") or f"trc_live_{uuid.uuid4().hex[:10]}")
    customer_id_raw = hello.get("customer_id")
    customer_id = str(customer_id_raw) if customer_id_raw else None

    log.info(
        "live ws hello trace=%s customer=%s", trace_id, customer_id or "anonymous"
    )

    session = voice_live_service.new_session(
        trace_id=trace_id, customer_id=customer_id
    )
    await session.start()

    # Two cooperative pumps — browser → session, session → browser.
    pumps = [
        asyncio.create_task(_pump_browser_to_session(ws, session), name="browser-up"),
        asyncio.create_task(_pump_session_to_browser(ws, session), name="browser-down"),
    ]

    try:
        # Whichever pump finishes first triggers shutdown of the other.
        done, pending = await asyncio.wait(
            pumps, return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()
        for t in pumps:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
    finally:
        await session.stop()
        try:
            await ws.close()
        except Exception:                              # noqa: BLE001 — best-effort
            pass


async def _pump_browser_to_session(ws: WebSocket, session: LiveSession) -> None:
    """Read JSON frames from the browser and forward to the Live session."""
    while True:
        try:
            text = await ws.receive_text()
        except WebSocketDisconnect:
            await session.inbound.put(None)
            return
        except Exception:                              # noqa: BLE001
            log.exception("ws receive failed trace=%s", session.trace_id)
            await session.inbound.put(None)
            return

        try:
            msg = json.loads(text)
        except json.JSONDecodeError:
            log.warning("non-JSON frame on live ws trace=%s", session.trace_id)
            continue

        mtype = msg.get("type")
        if mtype == "audio":
            data = msg.get("data") or ""
            try:
                pcm = base64.b64decode(data, validate=True)
            except (ValueError, TypeError):
                log.warning("audio frame not base64 trace=%s", session.trace_id)
                continue
            await session.inbound.put({"type": "audio", "pcm": pcm})
        elif mtype == "end_audio":
            await session.inbound.put({"type": "end_audio"})
        elif mtype == "close":
            await session.inbound.put(None)
            return
        else:
            log.debug(
                "unhandled inbound frame type=%s trace=%s", mtype, session.trace_id
            )


async def _pump_session_to_browser(ws: WebSocket, session: LiveSession) -> None:
    """Drain the session's outbound queue and emit JSON frames."""
    while True:
        item = await session.outbound.get()
        if item is None:
            return
        if isinstance(item, LiveOutboundAudio):
            payload: dict[str, Any] = {
                "type": "audio",
                "data": base64.b64encode(item.pcm_bytes).decode("ascii"),
            }
        elif isinstance(item, LiveOutboundEvent):
            payload = {"type": item.type, **item.payload}
        else:
            continue

        try:
            await ws.send_text(json.dumps(payload))
        except WebSocketDisconnect:
            return
        except Exception:                              # noqa: BLE001
            log.exception("ws send failed trace=%s", session.trace_id)
            return

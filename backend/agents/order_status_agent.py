"""OrderStatusAgent — looks up an order and synthesizes a grounded reply.

Tool flow:
  1. If the utterance contains an order number (`#1234` or `1234`):
       a. Look the order up directly in BigQuery (works for anonymous callers).
       b. If a `customer_id` is also known, verify the order belongs to that
          customer; otherwise just answer about the order.
  2. Otherwise, if the caller is identified, pull their 3 most-recent orders.
  3. Otherwise (anonymous + no order number) → ask for the order number.
  4. Pass the order rows as authoritative context to the synthesizer.
"""
from __future__ import annotations

import logging
import re
import time

from backend.agents.base import SpecialistOutput, ToolEvent
from backend.agents.synthesizer import synthesize
from backend.models.order import Order
from backend.repositories.order_repo import OrderRepository

log = logging.getLogger(__name__)

_ORDER_ID_RE = re.compile(r"#?\s*(\d{3,6})")


def _extract_order_id(utterance: str) -> str | None:
    """Look for a `#1234` style reference. Returns the canonical `#1234` form."""
    m = _ORDER_ID_RE.search(utterance)
    if not m:
        return None
    return f"#{m.group(1)}"


def _format_orders_context(orders: list[Order]) -> str:
    if not orders:
        return "(no orders found for this customer)"
    return "Recent orders for this customer (most recent first):\n" + "\n".join(
        f"- {o.as_context_block()}" for o in orders
    )


def handle(
    *,
    utterance: str,
    customer_id: str | None,
    order_repo: OrderRepository,
) -> SpecialistOutput:
    tool_events: list[ToolEvent] = []
    requested_id = _extract_order_id(utterance)

    # ── Path A: anonymous caller ───────────────────────────────────────
    # If the utterance contains an order number we can answer directly
    # by ID — exactly how a contact-center IVR handles "press your order
    # number to check status." Without an order number AND without a
    # caller, we have to ask for one.
    if customer_id is None:
        if requested_id is None:
            text = (
                "I can help look up an order — could you share the order number, "
                "or the phone number on the account?"
            )
            return SpecialistOutput(
                response_text=text,
                context="(no caller identified, no order number provided)",
                awaiting_slot=True,
                skip_grounding=True,
            )

        t0 = time.perf_counter()
        match = order_repo.get_order(requested_id)
        tool_events.append(
            ToolEvent(
                event_type="order_lookup",
                latency_ms=int((time.perf_counter() - t0) * 1000),
                metadata={
                    "customer_id":  None,
                    "order_id":     requested_id,
                    "found":        match is not None,
                    "lookup_mode":  "by_order_id",
                },
            )
        )
        if match is None:
            context = (
                f"The caller asked about order {requested_id}, but no order with "
                f"that ID exists in our system."
            )
        else:
            context = _format_orders_context([match])

        synth = synthesize(utterance=utterance, context=context)
        return SpecialistOutput(
            response_text=synth.response_text,
            context=context,
            synthesis=synth,
            tool_events=tool_events,
        )

    # ── Path B: identified caller ──────────────────────────────────────
    t0 = time.perf_counter()
    orders = order_repo.recent_orders_for_customer(customer_id)
    bq_latency_ms = int((time.perf_counter() - t0) * 1000)

    tool_events.append(
        ToolEvent(
            event_type="order_lookup",
            latency_ms=bq_latency_ms,
            metadata={
                "customer_id":  customer_id,
                "row_count":    len(orders),
                "order_ids":    [o.order_id for o in orders],
                "lookup_mode":  "recent_for_customer",
            },
        )
    )

    if requested_id is not None:
        match = next((o for o in orders if o.order_id == requested_id), None)
        if match is None:
            t1 = time.perf_counter()
            match = order_repo.get_order(requested_id)
            tool_events.append(
                ToolEvent(
                    event_type="order_lookup",
                    latency_ms=int((time.perf_counter() - t1) * 1000),
                    metadata={"order_id": requested_id, "found": match is not None},
                )
            )
        if match is not None and match.customer_id == customer_id:
            context = _format_orders_context([match])
        else:
            # Order doesn't match this customer — fall back to recent list and
            # let the synthesizer explain.
            context = (
                f"The customer asked about order {requested_id}, but no order "
                f"with that ID belongs to this customer.\n"
                + _format_orders_context(orders)
            )
    else:
        context = _format_orders_context(orders)

    synth = synthesize(utterance=utterance, context=context)

    return SpecialistOutput(
        response_text=synth.response_text,
        context=context,
        synthesis=synth,
        tool_events=tool_events,
    )

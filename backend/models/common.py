"""Shared enums and primitive types mirroring frontend/src/api/types.ts."""
from __future__ import annotations

from typing import Literal

LoyaltyTier = Literal["bronze", "silver", "gold"]
DisplayTier = Literal["bronze", "silver", "gold", "anonymous"]
Modality = Literal["voice", "chat"]
Journey = Literal[
    "order_status",
    "product_qa",
    "service_request",
    "escalate",
    "out_of_scope",
]
IntentOrAmbiguous = Literal[
    "order_status",
    "product_qa",
    "service_request",
    "escalate",
    "out_of_scope",
    "ambiguous",
]
Outcome = Literal["contained", "escalated", "refused", "in_progress"]
OrderStatus = Literal["placed", "shipped", "delivered", "returned"]
FailureType = Literal[
    "router_misroute",
    "retrieval_miss",
    "grounding_rejection",
    "over_eager_refusal",
    "lost_context",
    "tool_error",
]
EscalationReason = Literal[
    "low_confidence",
    "grounding_failed",
    "explicit_request",
    "out_of_scope",
    "turn_cap",
]
VerificationVerdict = Literal["pass", "fail"]

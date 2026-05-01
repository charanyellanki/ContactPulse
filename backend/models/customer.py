"""Customer models. PII posture: no name/email/phone — display_label only."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .common import Journey, LoyaltyTier


class CustomerSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str
    display_label: str
    tier: LoyaltyTier


class Customer(CustomerSummary):
    lifetime_value_usd: float
    open_orders: int
    recent_journey: Journey | None = None

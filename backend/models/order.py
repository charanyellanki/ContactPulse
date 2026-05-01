"""Order models — used by OrderStatusAgent.

The synthesizer never gets a raw Pydantic dump; we serialize via
`Order.as_context_block()` to keep the prompt compact.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

OrderStatus = Literal["delivered", "in_transit", "processing"]


class Order(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str
    customer_id: str
    sku: str
    product_name: str
    quantity: int
    status: OrderStatus
    order_date: str
    eta: str | None = None
    tracking_no: str | None = None

    def as_context_block(self) -> str:
        """Compact, fact-only string for prompt context. No prose."""
        bits = [
            f"order_id={self.order_id}",
            f"sku={self.sku}",
            f"product_name={self.product_name}",
            f"quantity={self.quantity}",
            f"status={self.status}",
            f"order_date={self.order_date}",
        ]
        if self.eta:
            bits.append(f"eta={self.eta}")
        if self.tracking_no:
            bits.append(f"tracking_no={self.tracking_no}")
        return ", ".join(bits)

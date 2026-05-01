import type { Customer } from "@/api/types";

/**
 * MOCK_CUSTOMERS — single source of truth for synthetic customer profiles.
 *
 * Production posture: no `name`, `email`, or `phone` field exists on the
 * Customer type. Operator-facing surfaces render `display_label` (a safe,
 * server-computed string) plus the `tier` badge. Personal identifiers stay
 * in the source-of-record system; the redacted projection is what the UI
 * sees. When the FastAPI /customers endpoint lands, it returns this exact
 * shape so the frontend swap is one import.
 */
export const MOCK_CUSTOMERS: Customer[] = [
  {
    customer_id: "1042",
    display_label: "Cust #1042 · Gold",
    tier: "gold",
    lifetime_value_usd: 12450,
    open_orders: 3,
    recent_journey: "order_status",
  },
  {
    customer_id: "2087",
    display_label: "Cust #2087 · Silver",
    tier: "silver",
    lifetime_value_usd: 4280,
    open_orders: 0,
    recent_journey: "product_qa",
  },
  {
    customer_id: "3391",
    display_label: "Cust #3391 · Bronze",
    tier: "bronze",
    lifetime_value_usd: 612,
    open_orders: 1,
    recent_journey: "product_qa",
  },
  {
    customer_id: "4156",
    display_label: "Cust #4156 · Gold",
    tier: "gold",
    lifetime_value_usd: 18920,
    open_orders: 2,
    recent_journey: "service_request",
  },
  {
    customer_id: "5203",
    display_label: "Cust #5203 · Silver",
    tier: "silver",
    lifetime_value_usd: 3105,
    open_orders: 0,
    recent_journey: "product_qa",
  },
  {
    customer_id: "6078",
    display_label: "Cust #6078 · Bronze",
    tier: "bronze",
    lifetime_value_usd: 248,
    open_orders: 0,
    recent_journey: null,
  },
];

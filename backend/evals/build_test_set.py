"""Generate the labeled eval test set.

Writes `backend/evals/test_set.jsonl` — 150 queries, 50 per journey:
  - order_status (50): order lookups, delivery questions, returns, cancellations
  - product_qa (50): 30 in-KB, 20 out-of-KB (refusal expected)
  - service_request (50): 15 fully-specified (single-turn completable),
                          35 missing slots (multi-turn slot-filling)

Each line is a JSON object matching the schema in CLAUDE.md task description:

    {
      "query_id": "ord_001",
      "journey": "order_status",
      "utterance": "...",
      "expected_intent": "order_status",
      "expected_outcome": "Contained",
      "must_contain": ["order"],
      "must_not_contain": ["I don't know"],
      "requires_grounding": false
    }

Deterministic — no randomness. Re-running produces the same output, so test_set.jsonl
should be committed alongside this script (the script is documentation of how the
test set was constructed).

Usage:
    python -m backend.evals.build_test_set
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


OUTPUT_PATH = Path(__file__).resolve().parent / "test_set.jsonl"


# ─── Order status (50) ────────────────────────────────────────────────────


# 25 with explicit order ID references — agent should attempt lookup
_ORDER_WITH_ID: list[tuple[str, str]] = [
    ("Where is my Milwaukee drill I ordered last week? Order #4521.",                      "Contained"),
    ("Can you check the status of order #7812?",                                            "Contained"),
    ("Has order #6677 shipped yet?",                                                        "Contained"),
    ("I need an update on order #9034 — when will it arrive?",                              "Contained"),
    ("My order #5512 says delivered but I never got it.",                                   "Contained"),
    ("What's the tracking number for order #3344?",                                         "Contained"),
    ("Order #2201 — is it still on time for Friday?",                                       "Contained"),
    ("Did order #8890 ship today?",                                                         "Contained"),
    ("I want to cancel order #4502 if it hasn't shipped.",                                  "Contained"),
    ("Can I change the delivery address on order #6128?",                                   "Contained"),
    ("Where is order #7755? It's been five days.",                                          "Contained"),
    ("Why is order #1199 still processing?",                                                "Contained"),
    ("Order number 4521 — was it delivered?",                                               "Contained"),
    ("Please look up order 8814 for me.",                                                   "Contained"),
    ("Can you tell me when order #3387 is expected?",                                       "Contained"),
    ("I haven't received order #2065 — can you check?",                                     "Contained"),
    ("Tracking on order #9912?",                                                            "Contained"),
    ("Order #1450, has it been picked up by the carrier?",                                  "Contained"),
    ("My order #5108 — what's the ETA?",                                                    "Contained"),
    ("I need to update the shipping address on #6677.",                                     "Contained"),
    ("Order #4321 status please.",                                                          "Contained"),
    ("When will my order #2238 ship?",                                                      "Contained"),
    ("Has order #7702 left the warehouse?",                                                 "Contained"),
    ("Order #8856, was it delayed?",                                                        "Contained"),
    ("I need the carrier name for order #3060.",                                            "Contained"),
]

# 15 generic order status (no ID) — agent should ask or look up recent orders
_ORDER_GENERIC: list[tuple[str, str]] = [
    ("Where's my order?",                                                                   "Contained"),
    ("Can you check on my recent order?",                                                   "Contained"),
    ("My package hasn't arrived yet.",                                                      "Contained"),
    ("When is my delivery coming?",                                                         "Contained"),
    ("I'd like an update on my last order.",                                                "Contained"),
    ("Is my order out for delivery today?",                                                 "Contained"),
    ("I'm waiting on a shipment, can you help?",                                            "Contained"),
    ("My order is late — what happened?",                                                   "Contained"),
    ("Can you tell me when my drill will arrive?",                                          "Contained"),
    ("I ordered a thermostat last week, where is it?",                                      "Contained"),
    ("Has my paint order shipped?",                                                         "Contained"),
    ("Looking for the status of my most recent purchase.",                                  "Contained"),
    ("I haven't gotten a shipping confirmation yet.",                                       "Contained"),
    ("Can you check what's going on with my recent purchase?",                              "Contained"),
    ("I want to know when my floodlight gets here.",                                        "Contained"),
]

# 10 special: returns, cancellations, wrong-item disambiguation
_ORDER_SPECIAL: list[tuple[str, str]] = [
    ("I got the wrong item — I ordered the X-200 drill but received an X-100.",             "Contained"),
    ("I need to return my recent order, can you start that?",                               "Contained"),
    ("Cancel my last order before it ships, please.",                                       "Contained"),
    ("The product arrived damaged. How do I return it?",                                    "Contained"),
    ("I need to swap the size on my recent order.",                                         "Contained"),
    ("Where do I drop off a return for an online order?",                                   "Contained"),
    ("I was charged twice for the same order — can you refund the duplicate?",              "Contained"),
    ("I want to cancel order #4521 and reorder a different model.",                         "Contained"),
    ("Can you reschedule the delivery for order #6128 to next week?",                       "Contained"),
    ("My order showed up with one item missing, how do I report that?",                     "Contained"),
]


# ─── Product QA (50) ──────────────────────────────────────────────────────


# 30 in-KB — agent should ground in the canned passages
_PQA_IN_KB: list[tuple[str, str]] = [
    ("What's the warranty on the Cordless Drill X-200?",                                    "Contained"),
    ("Does the X-200 drill come with a battery and charger?",                               "Contained"),
    ("Is the Cordless Drill X-200 brushless?",                                              "Contained"),
    ("What size chuck does the X-200 drill have?",                                          "Contained"),
    ("Is the X-200 drill compatible with other 20V batteries?",                             "Contained"),
    ("Does the X-200 have a work light?",                                                   "Contained"),
    ("Tell me about the X-200 drill's battery.",                                            "Contained"),
    ("How long is the warranty period for the X-200?",                                      "Contained"),
    ("What's your return policy on opened paint?",                                          "Contained"),
    ("Can I return paint after I've opened it?",                                            "Contained"),
    ("What's the return window for most products?",                                         "Contained"),
    ("Can I return an online order in-store?",                                              "Contained"),
    ("What's the return policy on major appliances?",                                       "Contained"),
    ("Do online returns require a receipt?",                                                "Contained"),
    ("How long do I have to return a power tool?",                                          "Contained"),
    ("Can I return paint by mail?",                                                         "Contained"),
    ("What does the standard manufacturer warranty cover for power tools?",                 "Contained"),
    ("How long is the warranty on outdoor power equipment?",                                "Contained"),
    ("Are blades and bits covered by the warranty?",                                        "Contained"),
    ("What's the warranty length on major appliances?",                                     "Contained"),
    ("Tell me about the extended protection plan.",                                         "Contained"),
    ("How long do I have to buy an extended protection plan after a sale?",                 "Contained"),
    ("Are batteries covered under warranty after 90 days?",                                 "Contained"),
    ("What's covered under the standard manufacturer warranty?",                            "Contained"),
    ("Are extended protection plans available on power tools?",                             "Contained"),
    ("Does opened paint qualify for a refund or only store credit?",                        "Contained"),
    ("How quickly do I have to return a major appliance?",                                  "Contained"),
    ("Can I get a refund on my X-200 if it breaks within 3 years?",                         "Contained"),
    ("Is the X-200 drill 20V?",                                                             "Contained"),
    ("Does the X-200 drill ship with a kit?",                                               "Contained"),
]

# 20 NOT in KB — refusal expected. These are realistic product questions
# our 3-passage stub KB does not cover.
_PQA_NOT_IN_KB: list[tuple[str, str]] = [
    ("Will the FL-90 floodlight work with my existing motion sensor?",                      "Refused"),
    ("How many lumens does the FL-90 LED floodlight produce?",                              "Refused"),
    ("Is the LED floodlight FL-90 dimmable?",                                               "Refused"),
    ("Can the smart thermostat T-300 work without a C-wire?",                               "Refused"),
    ("What temperature range does the T-300 thermostat support?",                           "Refused"),
    ("Is the T-300 thermostat compatible with Apple HomeKit?",                              "Refused"),
    ("Are the patio chairs PC-12 weather resistant?",                                       "Refused"),
    ("What's the weight capacity on PC-12 patio chairs?",                                   "Refused"),
    ("Do you offer a price match against Lowe's for the X-200?",                            "Refused"),
    ("Will you match Amazon's price on the LED floodlight?",                                "Refused"),
    ("Is installation included when I buy the WH-40 water heater?",                         "Refused"),
    ("Does the dishwasher DW-18 come with a stainless steel hose?",                         "Refused"),
    ("Can you check stock at my local store for the CF-24 ceiling fan?",                    "Refused"),
    ("Is the LM-55 lawn mower self-propelled?",                                             "Refused"),
    ("How long is the LM-55 mower's deck?",                                                 "Refused"),
    ("Does the WH-40 qualify for the federal energy tax credit?",                           "Refused"),
    ("What's the noise rating in decibels for the DW-18 dishwasher?",                       "Refused"),
    ("How many cubic feet is the dishwasher DW-18?",                                        "Refused"),
    ("Can the CF-24 ceiling fan be installed on a sloped ceiling?",                         "Refused"),
    ("Is the LED floodlight FL-90 outdoor rated?",                                          "Refused"),
]


# ─── Service request (50) ─────────────────────────────────────────────────


# 15 fully-specified — agent has all 3 slots, can synthesize confirmation
_SR_COMPLETE: list[tuple[str, str]] = [
    ("Schedule a water heater installation for next Tuesday at 123 Main Street, Springfield IL.", "Contained"),
    ("I'd like to book an HVAC repair on Friday morning at 488 Oak Lane, Austin TX.",      "Contained"),
    ("Please set up a kitchen cabinet consultation next Wednesday at 91 Pine Road, Denver CO.", "Contained"),
    ("Book a dishwasher install Thursday afternoon at 220 Elm Street, Portland OR.",       "Contained"),
    ("Schedule ceiling fan installation Saturday at 17 Maple Court, Boston MA.",           "Contained"),
    ("Book a flooring measurement appointment Tuesday at 503 Birch Avenue, Seattle WA.",   "Contained"),
    ("Set up a water softener install for next Monday at 76 Cedar Drive, Miami FL.",       "Contained"),
    ("Schedule a window installation consultation Friday at 312 Hickory Lane, Atlanta GA.", "Contained"),
    ("Book a refrigerator install Tuesday morning at 8 Spruce Court, Phoenix AZ.",          "Contained"),
    ("Please schedule a roofing inspection next Thursday at 145 Walnut Street, Dallas TX.", "Contained"),
    ("Book a microwave installation Wednesday afternoon at 660 Aspen Way, Chicago IL.",     "Contained"),
    ("Schedule a tankless water heater install for Friday at 22 Magnolia Lane, Charlotte NC.", "Contained"),
    ("Set up a garage door repair Monday at 99 Sycamore Court, Nashville TN.",              "Contained"),
    ("Book a kitchen sink replacement next Tuesday at 401 Willow Drive, Raleigh NC.",       "Contained"),
    ("Please schedule an attic insulation consultation Saturday at 277 Beech Lane, San Diego CA.", "Contained"),
]

# 35 missing slots — agent should ask a clarifying question
_SR_MISSING: list[tuple[str, str]] = [
    ("I'd like to schedule an installation for a water heater.",                            "Contained"),
    ("Can someone come out next week to look at my HVAC?",                                  "Contained"),
    ("I need to book a consultation for kitchen cabinets.",                                 "Contained"),
    ("Schedule a repair visit for my dishwasher please.",                                   "Contained"),
    ("I want to set up a service appointment for ceiling fan install.",                     "Contained"),
    ("Can you book a flooring measurement?",                                                "Contained"),
    ("I need help with a water heater replacement.",                                        "Contained"),
    ("Schedule an installer for my new microwave.",                                         "Contained"),
    ("I need a window replacement consultation.",                                           "Contained"),
    ("Book me a plumber.",                                                                  "Contained"),
    ("Can someone install my new dishwasher?",                                              "Contained"),
    ("I'd like to book an appointment for a fridge install.",                               "Contained"),
    ("Please send a tech to look at my garage door.",                                       "Contained"),
    ("Can I schedule a kitchen consultation for next week?",                                "Contained"),
    ("I need an installer for my tankless water heater.",                                   "Contained"),
    ("Book a service appointment please.",                                                  "Contained"),
    ("I want to schedule installation services.",                                           "Contained"),
    ("Can you book a contractor for me?",                                                   "Contained"),
    ("I'd like to book HVAC service.",                                                      "Contained"),
    ("Schedule a flooring install.",                                                        "Contained"),
    ("I need a quote for kitchen cabinets.",                                                "Contained"),
    ("Can you set up an attic insulation consult?",                                         "Contained"),
    ("Book a roofing inspection for me.",                                                   "Contained"),
    ("Schedule a sink replacement.",                                                        "Contained"),
    ("I need someone to install a ceiling fan in my living room.",                          "Contained"),
    ("Can you arrange a water softener install?",                                           "Contained"),
    ("Book a measurement for new flooring.",                                                "Contained"),
    ("I'd like installation services for my new appliances.",                               "Contained"),
    ("Schedule a consultation about kitchen remodeling.",                                   "Contained"),
    ("Can someone replace my faucet?",                                                      "Contained"),
    ("I need a bath install booked.",                                                       "Contained"),
    ("Schedule a window measurement appointment.",                                          "Contained"),
    ("Book a deck consultation.",                                                           "Contained"),
    ("Can I get a smart thermostat installed?",                                             "Contained"),
    ("I need to book a handyman service for next Saturday.",                                "Contained"),
]


# ─── Builders ─────────────────────────────────────────────────────────────


def _ord_must_contain(utt: str) -> list[str]:
    """Pick lenient must-contain tokens — anything plausibly in a competent reply."""
    if "cancel" in utt.lower():
        return ["cancel"]
    if "return" in utt.lower():
        return ["return"]
    if "address" in utt.lower():
        return ["address"]
    if "tracking" in utt.lower():
        return ["track"]
    return ["order"]


def _build_order_status() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seq = 1
    for source in (_ORDER_WITH_ID, _ORDER_GENERIC, _ORDER_SPECIAL):
        for utt, outcome in source:
            items.append(
                {
                    "query_id":           f"ord_{seq:03d}",
                    "journey":            "order_status",
                    "utterance":          utt,
                    "expected_intent":    "order_status",
                    "expected_outcome":   outcome,
                    "must_contain":       _ord_must_contain(utt),
                    "must_not_contain":   ["I don't know", "cannot help"],
                    "requires_grounding": True,
                }
            )
            seq += 1
    assert len(items) == 50, f"expected 50 order_status, got {len(items)}"
    return items


def _build_product_qa() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seq = 1
    for utt, outcome in _PQA_IN_KB:
        items.append(
            {
                "query_id":           f"pqa_{seq:03d}",
                "journey":            "product_qa",
                "utterance":          utt,
                "expected_intent":    "product_qa",
                "expected_outcome":   outcome,
                "must_contain":       [],  # KB content varies — no hard string check
                "must_not_contain":   ["I don't know", "cannot help"],
                "requires_grounding": True,
            }
        )
        seq += 1
    for utt, outcome in _PQA_NOT_IN_KB:
        items.append(
            {
                "query_id":           f"pqa_{seq:03d}",
                "journey":            "product_qa",
                "utterance":          utt,
                "expected_intent":    "product_qa",
                "expected_outcome":   outcome,
                "must_contain":       [],
                "must_not_contain":   [],
                "requires_grounding": True,
            }
        )
        seq += 1
    assert len(items) == 50, f"expected 50 product_qa, got {len(items)}"
    return items


def _build_service_request() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seq = 1
    for utt, outcome in _SR_COMPLETE:
        items.append(
            {
                "query_id":           f"svc_{seq:03d}",
                "journey":            "service_request",
                "utterance":          utt,
                "expected_intent":    "service_request",
                "expected_outcome":   outcome,
                "must_contain":       [],
                "must_not_contain":   ["I don't know"],
                "requires_grounding": False,
            }
        )
        seq += 1
    for utt, outcome in _SR_MISSING:
        items.append(
            {
                "query_id":           f"svc_{seq:03d}",
                "journey":            "service_request",
                "utterance":          utt,
                "expected_intent":    "service_request",
                "expected_outcome":   outcome,
                "must_contain":       [],
                "must_not_contain":   ["I don't know"],
                "requires_grounding": False,
            }
        )
        seq += 1
    assert len(items) == 50, f"expected 50 service_request, got {len(items)}"
    return items


def build() -> list[dict[str, Any]]:
    items = _build_order_status() + _build_product_qa() + _build_service_request()
    assert len(items) == 150, f"expected 150 total, got {len(items)}"
    return items


def main() -> int:
    items = build()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"wrote {len(items)} queries to {OUTPUT_PATH}")
    by_journey: dict[str, int] = {}
    for it in items:
        by_journey[it["journey"]] = by_journey.get(it["journey"], 0) + 1
    for j, n in by_journey.items():
        print(f"  {j}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Generate the fake shop database for the demo agent with great-generator.

    pip install -e ".[data]"
    python examples/shop_agent/make_data.py

No real customer data is used anywhere: great-generator builds realistic synthetic rows.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from great_generator import generate_relational

STATUSES = ["shipped", "delivered", "processing", "cancelled", "refunded"]
NOTES = [
    "Prefers delivery after 6 pm.",
    "Gift order, no invoice in the box.",
    "Asked twice about the delivery date.",
    "Leave the parcel with the security guard.",
    "",
]


def main() -> None:
    tables = generate_relational(
        {
            "customers": {
                "schema": {"customer_id": "string", "name": "string", "city": "string"},
                "primary_key": "customer_id",
            },
            "orders": {
                "schema": {"order_id": "string", "customer_id": "string", "amount": "float"},
                "primary_key": "order_id",
            },
        },
        relationships=["orders.customer_id -> customers.customer_id"],
        rows={"customers": 6, "orders": 12},
        seed=42,
    )
    rng = random.Random(42)
    customers = {str(c["customer_id"]): c for c in tables["customers"].to_dict("records")}
    orders = {}
    for o in tables["orders"].to_dict("records"):
        c = customers[str(o["customer_id"])]
        oid = f"A{int(o['order_id']):03d}"
        orders[oid] = {
            "order_id": oid,
            "customer": c["name"],
            "city": c["city"],
            "amount_inr": round(float(o["amount"]) * 40, 2),
            "status": rng.choice(STATUSES),
            "note": rng.choice(NOTES),
        }
    out = Path(__file__).parent / "data" / "orders.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(orders, indent=2))
    print(f"wrote {len(orders)} orders to {out}")


if __name__ == "__main__":
    main()

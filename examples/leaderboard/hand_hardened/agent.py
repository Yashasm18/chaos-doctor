"""Pattern: an agent a careful developer already hardened by hand (try/except + retry loop).

Written from scratch for the Chaos Doctor leaderboard, to check that the scanner gives credit
for defences it didn't add, and to show which attacks hand-written handling still misses.
"""

import json
import time

from chaos_doctor.simulated import SimulatedClient

client = SimulatedClient()

PARCELS = {
    "P1": {"parcel": "P1", "customer": "Sam", "status": "in transit"},
    "P2": {"parcel": "P2", "customer": "Ira", "status": "delivered"},
    "P3": {"parcel": "P3", "customer": "Tom", "status": "held at customs"},
}

TOOLS = ["tracking_api"]
TASKS = [{"parcel": "P1"}, {"parcel": "P2"}, {"parcel": "P3"}]


def tracking_api(parcel_id):
    """Tool: courier tracking lookup."""
    return dict(PARCELS[parcel_id])


def get_parcel(parcel_id):
    for attempt in range(3):
        try:
            return tracking_api(parcel_id)
        except Exception:
            time.sleep(0.05 * (attempt + 1))
    return None


def call_model(prompt):
    for attempt in range(3):
        try:
            r = client.chat.completions.create(
                model="simulated", messages=[{"role": "user", "content": prompt}]
            )
            return r.choices[0].message.content
        except Exception:
            time.sleep(0.05 * (attempt + 1))
    return "Sorry, please try again later."


def run(task):
    parcel = get_parcel(task["parcel"])
    return call_model(f"Update the customer on their parcel. Details: {json.dumps(parcel)}")


def check(task, reply):
    return isinstance(reply, str) and PARCELS[task["parcel"]]["status"] in reply.lower()

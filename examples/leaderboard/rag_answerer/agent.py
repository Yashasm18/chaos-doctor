"""Pattern: retrieval-augmented answerer. Search a knowledge base, then answer from the hit.

Written from scratch for the Chaos Doctor leaderboard; it follows the RAG shape most
tutorials use (retrieve -> stuff the context into the prompt -> one model call).
"""

import json

from chaos_doctor.simulated import SimulatedClient

client = SimulatedClient()

KB = [
    {"doc": "refund-policy", "status": "approved", "text": "Refunds within 30 days are approved."},
    {"doc": "shipping-times", "status": "on schedule", "text": "Orders ship in 2 days."},
    {"doc": "warranty", "status": "active", "text": "Hardware warranty lasts 1 year."},
]

TOOLS = ["search_kb"]
TASKS = [{"q": "refund"}, {"q": "shipping"}, {"q": "warranty"}]


def search_kb(query):
    """Tool: keyword search over the knowledge base."""
    return next(dict(d) for d in KB if query in d["doc"])


def retrieve(query):
    return search_kb(query)


def answer(prompt):
    r = client.chat.completions.create(
        model="simulated", messages=[{"role": "user", "content": prompt}]
    )
    return r.choices[0].message.content


def run(task):
    hit = retrieve(task["q"])
    return answer(f"Answer using only this context. Details: {json.dumps(hit)}")


def check(task, reply):
    hit = next(d for d in KB if task["q"] in d["doc"])
    return isinstance(reply, str) and hit["status"] in reply.lower()

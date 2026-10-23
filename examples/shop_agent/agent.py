"""Shop support agent: the demo "victim" for Chaos Doctor.

It answers "where is my order?" by looking the order up and asking an LLM to reply.
It is deliberately fragile: no retries, no timeouts, no output checks, no input cleaning.

LLM backend:
  - CHAOS_DOCTOR_VICTIM_MODEL unset: simulated_llm.py (fast, offline, deterministic).
  - CHAOS_DOCTOR_VICTIM_MODEL=qwen3:0.6b (or any Ollama model): a real local model.
"""

import json
import os
from pathlib import Path

from openai import OpenAI
from simulated_llm import SimulatedClient

ORDERS = json.loads((Path(__file__).parent / "data" / "orders.json").read_text())
VICTIM_MODEL = os.environ.get("CHAOS_DOCTOR_VICTIM_MODEL", "")

if VICTIM_MODEL:
    base = os.environ.get("CHAOS_DOCTOR_OLLAMA_URL", "http://localhost:11434").rstrip("/")
    client = OpenAI(base_url=f"{base}/v1", api_key="ollama")
else:
    client = SimulatedClient()

TOOLS = ["lookup_order"]
TASKS = [
    {"order_id": "A001", "question": "Where is my order?"},
    {"order_id": "A004", "question": "Has my order shipped yet?"},
    {"order_id": "A007", "question": "What is the status of my order?"},
]


def lookup_order(order_id):
    """Tool: fetch one order from the shop database."""
    return dict(ORDERS[order_id])


def get_order(order_id):
    """Look up the customer's order."""
    return lookup_order(order_id)


def ask_llm(prompt):
    """Send the prompt to the model and return its text reply."""
    resp = client.chat.completions.create(
        model=VICTIM_MODEL or "simulated",
        messages=[
            {"role": "system", "content": "You are a friendly shop support assistant."},
            {"role": "user", "content": prompt},
        ],
    )
    return resp.choices[0].message.content


def run(task):
    order = get_order(task["order_id"])
    prompt = (
        f"Customer question: {task['question']}\n"
        f"Order details: {json.dumps(order)}\n"
        "Answer in one short sentence and mention the order status."
    )
    return ask_llm(prompt)


def check(task, answer):
    """Task passes when the reply states the correct order status."""
    status = ORDERS[task["order_id"]]["status"]
    return isinstance(answer, str) and status in answer.lower()

"""A simulated chat model for the demo agent: fast, offline and deterministic.

It answers like a small, obedient model: it states the order status, and it follows
instructions it finds in the prompt (which is exactly what makes prompt injection work).
Kept out of agent.py so the Doctor and Attacker only see the agent's real logic.
"""

import json
import re
import time

from openai.types.chat import ChatCompletion


class _Completions:
    def create(self, model, messages, **kwargs):
        prompt = messages[-1]["content"]
        obey = re.search(r"reply only with\s+([A-Z0-9\-]+)", prompt, re.IGNORECASE)
        if obey:
            text = obey.group(1)
        else:
            match = re.search(r"Order details: (\{.*\})", prompt)
            order = json.loads(match.group(1)) if match else None
            if order:
                text = (
                    f"Hi {order['customer']}, your order {order['order_id']} is {order['status']}."
                )
            else:
                text = "Sorry, I could not find that order."
        return ChatCompletion.model_validate(
            {
                "id": "sim",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "simulated",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": text},
                    }
                ],
            }
        )


class SimulatedClient:
    """Duck-types the part of openai.OpenAI the agent uses: chat.completions.create."""

    def __init__(self):
        self.chat = type("Chat", (), {"completions": _Completions()})()

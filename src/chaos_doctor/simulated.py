"""A simulated chat model for example and benchmark agents: fast, offline, deterministic.

It reads the JSON after "details:" in the prompt and states its status, and it obeys
"reply only with X" instructions it finds, which is exactly what makes prompt injection work.
"""

from __future__ import annotations

import json
import re
import time

from openai.types.chat import ChatCompletion

_OBEY = re.compile(r"reply only with\s+([A-Z0-9\-]+)", re.IGNORECASE)
_DETAILS = re.compile(r"details:\s*(\{.*\})", re.IGNORECASE)


def _reply(prompt: str) -> str:
    obey = _OBEY.search(prompt)
    if obey:
        return obey.group(1)
    match = _DETAILS.search(prompt)
    data = json.loads(match.group(1)) if match else None
    if not isinstance(data, dict) or "status" not in data:
        return "Sorry, I could not find that."
    who = next((data[k] for k in ("customer", "name", "passenger", "requester") if k in data), "")
    return f"Hi {who}, the current status is {data['status']}.".replace("Hi ,", "Hi,")


class _Completions:
    def create(self, model, messages, **kwargs):
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
                        "message": {
                            "role": "assistant",
                            "content": _reply(messages[-1]["content"]),
                        },
                    }
                ],
            }
        )


class SimulatedClient:
    """Duck-types the part of openai.OpenAI agents use: chat.completions.create."""

    def __init__(self) -> None:
        self.chat = type("Chat", (), {"completions": _Completions()})()

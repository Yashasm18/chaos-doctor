"""Talks to a local open-weight model through Ollama.

The Doctor and the Attacker use Ollama's native /api/chat endpoint with a JSON schema in
`format`, so every reply is parseable JSON that matches the schema.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

import httpx

from chaos_doctor.config import Settings


class LLMError(RuntimeError):
    pass


class JsonLLM(Protocol):
    def __call__(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]: ...


class OllamaJSON:
    """Callable that returns a dict matching `schema`."""

    def __init__(self, settings: Settings, timeout_s: float = 180.0) -> None:
        self.settings = settings
        self.timeout_s = timeout_s

    def __call__(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        body = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "format": schema,
            "stream": False,
            # Qwen3 is a reasoning model; skip the long think phase for snappy, structured replies.
            "think": False,
            # Short, focused replies keep a battle round fast on a laptop.
            "options": {"temperature": 0.2, "num_predict": 400, "num_ctx": 8192},
            "keep_alive": "30m",
        }
        try:
            resp = httpx.post(
                f"{self.settings.ollama_url}/api/chat", json=body, timeout=self.timeout_s
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(
                f"Could not reach Ollama at {self.settings.ollama_url} "
                f"(model {self.settings.model}). Is `ollama serve` running? ({exc})"
            ) from exc
        content = resp.json().get("message", {}).get("content", "")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Model returned invalid JSON: {content[:200]!r}") from exc

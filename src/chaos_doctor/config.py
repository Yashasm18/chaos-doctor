"""Runtime settings, all overridable with environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    ollama_url: str
    model: str
    trials: int
    target_score: int
    max_rounds: int


def load_settings() -> Settings:
    return Settings(
        # Point this at a teammate's machine to share one model server,
        # e.g. CHAOS_DOCTOR_OLLAMA_URL=http://192.168.1.25:11434
        ollama_url=os.environ.get("CHAOS_DOCTOR_OLLAMA_URL", "http://localhost:11434").rstrip("/"),
        # qwen3:8b is the default; use qwen3:4b on 8 GB laptops.
        model=os.environ.get("CHAOS_DOCTOR_MODEL", "qwen3:8b"),
        trials=int(os.environ.get("CHAOS_DOCTOR_TRIALS", "3")),
        target_score=int(os.environ.get("CHAOS_DOCTOR_TARGET", "90")),
        max_rounds=int(os.environ.get("CHAOS_DOCTOR_ROUNDS", "5")),
    )

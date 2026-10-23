"""The fixed catalogue of fix recipes the Doctor chooses from.

Keeping the Doctor to a menu is what makes a small model reliable: it classifies the failure
and picks parameters; the decorator template does the actual code change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Recipe:
    name: str
    summary: str
    fixes: tuple[str, ...]
    defaults: dict[str, Any] = field(default_factory=dict)
    bounds: dict[str, tuple[float, float]] = field(default_factory=dict)

    def decorator(self, params: dict[str, Any]) -> str:
        if not self.defaults:
            return f"@guards.{self.name}"
        args = ", ".join(f"{k}={params[k]!r}" for k in self.defaults)
        return f"@guards.{self.name}({args})"

    def clean_params(self, params: dict[str, Any] | None) -> dict[str, Any]:
        params = params or {}
        out: dict[str, Any] = {}
        for key, default in self.defaults.items():
            value = params.get(key, default)
            if key not in self.bounds:
                out[key] = value if isinstance(value, (str, int, float, type(None))) else default
                continue
            try:
                value = type(default)(value)
            except (TypeError, ValueError):
                value = default
            lo, hi = self.bounds[key]
            out[key] = min(max(value, type(default)(lo)), type(default)(hi))
        return out


RECIPES: dict[str, Recipe] = {
    r.name: r
    for r in [
        Recipe(
            "retry",
            "Retry the call with exponential backoff",
            ("rate_limit_storm", "token_timeout", "tool_failure", "context_length"),
            {"attempts": 4, "backoff_s": 0.05},
            {"attempts": (2, 6), "backoff_s": (0.0, 2.0)},
        ),
        Recipe(
            "timeout",
            "Fail fast instead of waiting on a hung call",
            ("token_timeout",),
            {"seconds": 5.0},
            {"seconds": (0.5, 30.0)},
        ),
        Recipe(
            "fallback",
            "Return a safe default instead of crashing",
            ("tool_failure",),
            {"value": None},
        ),
        Recipe(
            "validate_output",
            "Re-ask the model when its output looks garbled",
            ("silent_degradation",),
            {"retries": 3},
            {"retries": (1, 5)},
        ),
        Recipe(
            "trim_prompt",
            "Shorten the prompt and retry on a context-length error",
            ("context_length",),
            {"max_chars": 2000},
            {"max_chars": (200, 20000)},
        ),
        Recipe(
            "sanitize",
            "Strip prompt-injection lines from tool results",
            ("prompt_injection",),
        ),
    ]
}

# Outermost first. retry wraps timeout so each attempt gets its own deadline;
# validate_output sits outside retry so a garbled-but-successful reply is re-asked.
DECORATOR_ORDER = ["validate_output", "sanitize", "fallback", "retry", "trim_prompt", "timeout"]

DEFAULT_RECIPE_FOR = {
    "rate_limit_storm": "retry",
    "token_timeout": "retry",
    "tool_failure": "retry",
    "context_length": "retry",
    "silent_degradation": "validate_output",
    "prompt_injection": "sanitize",
}

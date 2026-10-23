"""Resilience guards: the building blocks the Doctor's fix recipes insert into agent code.

Each guard is a decorator factory. The Doctor never writes free-form code; it picks a recipe,
a target function and parameters, and the patcher adds one of these decorators.
"""

from __future__ import annotations

import concurrent.futures
import functools
import re
import time
from collections.abc import Callable
from typing import Any

INJECTION_PATTERNS = [
    r"ignore (all |any )?(previous|prior|above) instructions",
    r"disregard (all |any )?(previous|prior|above)",
    r"you are now",
    r"system prompt",
    r"reply only with",
]


def retry(attempts: int = 3, backoff_s: float = 0.2) -> Callable:
    """Retry on any exception with exponential backoff."""

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            for i in range(attempts):
                try:
                    return fn(*args, **kwargs)
                except Exception:
                    if i == attempts - 1:
                        raise
                    time.sleep(backoff_s * (2**i))
            return None

        return wrapper

    return deco


def timeout(seconds: float = 5.0) -> Callable:
    """Fail fast with TimeoutError instead of waiting on a hung call."""

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = pool.submit(fn, *args, **kwargs)
            try:
                return future.result(timeout=seconds)
            except concurrent.futures.TimeoutError as exc:
                raise TimeoutError(f"{fn.__name__} took longer than {seconds}s") from exc
            finally:
                pool.shutdown(wait=False, cancel_futures=True)

        return wrapper

    return deco


def fallback(value: Any = None) -> Callable:
    """Return `value` instead of crashing when the call fails."""

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return fn(*args, **kwargs)
            except Exception:
                return value

        return wrapper

    return deco


COMMON_WORDS = set(
    """a an the and or but if of to in on at for from by with about as is are was were be been
    it its this that these those i you he she we they me my your our their his her them us
    not no yes do does did done have has had will would can could should may might must
    hi hello thanks thank please sorry sure here there what when where which who why how
    order orders status shipped delivered processing cancelled refunded arrive arrives
    today tomorrow soon now still yet just already one two all any some more very""".split()
)


def looks_garbled(text: str) -> bool:
    """Heuristic: real replies contain some common English words; scrambled text doesn't."""
    if not text or not text.strip():
        return True
    words = re.findall(r"[a-z']+", text.lower())
    if not words:
        return True
    common = sum(w in COMMON_WORDS for w in words)
    return common / len(words) < 0.2


def validate_output(retries: int = 2) -> Callable:
    """Re-ask when the model's text output looks corrupted."""

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            out = fn(*args, **kwargs)
            for _ in range(retries):
                if not (isinstance(out, str) and looks_garbled(out)):
                    return out
                out = fn(*args, **kwargs)
            return out

        return wrapper

    return deco


def trim_prompt(max_chars: int = 2000) -> Callable:
    """On a context-length error, retry once with the first string argument shortened."""

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                if "context" not in (type(exc).__name__ + str(exc)).lower():
                    raise
                trimmed = [a[-max_chars:] if isinstance(a, str) else a for a in args]
                return fn(*trimmed, **kwargs)

        return wrapper

    return deco


def strip_injection(text: str) -> str:
    lines = [
        line
        for line in text.splitlines()
        if not any(re.search(p, line, re.IGNORECASE) for p in INJECTION_PATTERNS)
    ]
    return "\n".join(lines)


def _clean(obj: Any) -> Any:
    if isinstance(obj, str):
        return strip_injection(obj)
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj


def sanitize(fn: Callable) -> Callable:
    """Drop prompt-injection lines from tool results before they reach the model."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return _clean(fn(*args, **kwargs))

    return wrapper

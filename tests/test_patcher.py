import ast

import pytest

from chaos_doctor.patcher import apply_recipe, diff, list_functions

SOURCE = '''"""Tiny agent."""
import json


def lookup(x):
    return {"x": x}


def get(x):
    return lookup(x)


def ask(prompt):
    return client.chat.completions.create(messages=[prompt])
'''


def test_list_functions_finds_call_sites():
    fns = {f.name: f for f in list_functions(SOURCE)}
    assert fns["ask"].calls_llm
    assert "lookup" in fns["get"].calls


def test_apply_adds_decorator_and_import():
    out = apply_recipe(SOURCE, "ask", "retry", {"attempts": 3})
    ast.parse(out)
    assert "from chaos_doctor import guards" in out
    assert "@guards.retry(attempts=3, backoff_s=0.05)\ndef ask" in out


def test_guards_are_stacked_in_safe_order():
    out = apply_recipe(SOURCE, "ask", "retry", {})
    out = apply_recipe(out, "ask", "validate_output", {})
    out = apply_recipe(out, "ask", "timeout", {"seconds": 2})
    block = out.split("def ask")[0].strip().splitlines()[-3:]
    assert [line.split("(")[0] for line in block] == [
        "@guards.validate_output",
        "@guards.retry",
        "@guards.timeout",
    ]


def test_reapplying_updates_params_instead_of_duplicating():
    out = apply_recipe(SOURCE, "ask", "retry", {"attempts": 2})
    out = apply_recipe(out, "ask", "retry", {"attempts": 6})
    assert out.count("@guards.retry") == 1
    assert "attempts=6" in out


def test_params_are_clamped():
    out = apply_recipe(SOURCE, "ask", "retry", {"attempts": 999})
    assert "attempts=6" in out


def test_unknown_function_raises():
    with pytest.raises(ValueError):
        apply_recipe(SOURCE, "nope", "retry", {})


def test_diff_is_unified():
    out = apply_recipe(SOURCE, "ask", "retry", {})
    d = diff(SOURCE, out)
    assert d.startswith("--- a/agent.py")
    assert "+@guards.retry" in d

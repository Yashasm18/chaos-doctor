"""The Doctor AI: reads a failure, names the root cause, and picks a fix recipe."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from chaos_doctor.llm import JsonLLM
from chaos_doctor.patcher import FunctionInfo, list_functions
from chaos_doctor.recipes import DEFAULT_RECIPE_FOR, RECIPES
from chaos_doctor.scan import AttackResult

SYSTEM = """You are Chaos Doctor, an expert in making LLM agents resilient.
You are given an agent's source code and a failure observed while faults were injected.
Find the root cause and choose ONE fix from the recipe menu, applied to ONE function.
Rules:
- Pick the function where the failing call happens (the function that calls the LLM for LLM
  faults, or the function that calls the failing tool for tool faults). Never pick the tool
  function itself.
- If the function already has the right guard but the attack still beats it, pick that
  same recipe with STRONGER parameters (for example more retry attempts).
- Keep parameters modest: small retry counts and short backoffs.
- Keep root_cause and explanation to one short sentence each.
Reply with JSON only."""


@dataclass
class Diagnosis:
    root_cause: str
    target_function: str
    recipe: str
    params: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5
    explanation: str = ""
    source: str = "llm"  # "llm" or "rules"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _schema(functions: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "root_cause": {"type": "string"},
            "target_function": {"type": "string", "enum": functions},
            "recipe": {"type": "string", "enum": list(RECIPES)},
            "params": {
                "type": "object",
                "properties": {
                    "attempts": {"type": "integer"},
                    "backoff_s": {"type": "number"},
                    "seconds": {"type": "number"},
                    "retries": {"type": "integer"},
                    "max_chars": {"type": "integer"},
                },
            },
            "confidence": {"type": "number"},
            "explanation": {"type": "string"},
        },
        "required": ["root_cause", "target_function", "recipe", "confidence", "explanation"],
    }


def _call_site(functions: list[FunctionInfo], target: str) -> FunctionInfo | None:
    """The function that makes the failing call: LLM caller, or caller of the tool."""
    for fn in functions:
        if fn.name == target:
            continue
        if (target == "llm" and fn.calls_llm) or (target != "llm" and target in fn.calls):
            return fn
    return None


def rule_based(source: str, failure: AttackResult) -> Diagnosis:
    """Deterministic baseline: used offline, in tests, and as a safety net for the LLM."""
    functions = list_functions(source)
    attack = failure.attack
    site = _call_site(functions, attack.target)
    recipe = DEFAULT_RECIPE_FOR[attack.kind]
    params = dict(RECIPES[recipe].defaults)
    name = site.name if site else functions[0].name
    cause = f"{attack.label} is not handled in {name}()"
    if site and recipe in site.guards:
        # The obvious guard is there but too weak for this attack: make it stronger.
        cause = f"{name}() has {recipe} but it gives up before {attack.label} clears"
        if recipe == "retry":
            params["attempts"] = RECIPES["retry"].bounds["attempts"][1]
        elif recipe == "validate_output":
            params["retries"] = RECIPES["validate_output"].bounds["retries"][1]
    return Diagnosis(
        root_cause=cause,
        target_function=name,
        recipe=recipe,
        params=params,
        confidence=0.6,
        explanation=f"Apply {recipe}{params} to {name}() so {attack.kind} no longer escapes.",
        source="rules",
    )


def diagnose(llm: JsonLLM | None, source: str, failure: AttackResult) -> Diagnosis:
    if llm is None:
        return rule_based(source, failure)
    functions = list_functions(source)
    names = [f.name for f in functions]
    menu = {
        name: {"what": r.summary, "fixes": list(r.fixes), "params": r.defaults}
        for name, r in RECIPES.items()
    }
    user = json.dumps(
        {
            "failure": {
                "attack": failure.attack.to_dict(),
                "passed": f"{failure.passes}/{failure.trials}",
                "observed_errors": failure.failures[:3],
            },
            "functions": [
                {
                    "name": f.name,
                    "doc": f.doc,
                    "calls": f.calls,
                    "calls_llm": f.calls_llm,
                    "existing_guards": f.guard_code,
                }
                for f in functions
            ],
            "recipe_menu": menu,
            "agent_source": source,
        },
        indent=1,
    )
    reply = llm(SYSTEM, user, _schema(names))
    diag = Diagnosis(
        root_cause=str(reply.get("root_cause", "")),
        target_function=str(reply.get("target_function", "")),
        recipe=str(reply.get("recipe", "")),
        params=dict(reply.get("params") or {}),
        confidence=float(reply.get("confidence", 0.5) or 0.5),
        explanation=str(reply.get("explanation", "")),
    )
    tool_names = {failure.attack.target}
    if (
        diag.target_function not in names
        or diag.recipe not in RECIPES
        or (diag.target_function in tool_names)
    ):
        safe = rule_based(source, failure)
        safe.root_cause = diag.root_cause or safe.root_cause
        safe.explanation = f"(model suggestion was invalid, used rules) {safe.explanation}"
        return safe
    # Guards only work where the failing call is made: a tool guard must wrap the tool's
    # caller, an LLM guard the function that calls the model. Correct the placement if needed.
    site = _call_site(functions, failure.attack.target)
    if site and diag.target_function != site.name:
        diag.explanation = (
            f"(placement corrected from {diag.target_function}() to {site.name}(), "
            f"where the failing call is made) {diag.explanation}"
        )
        diag.target_function = site.name
    return diag

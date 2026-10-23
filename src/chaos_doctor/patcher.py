"""Apply a recipe to agent source code: add (or update) one guard decorator on one function.

Edits are made with the `ast` line numbers, so the result is always valid Python and the
change is a small, reviewable diff.
"""

from __future__ import annotations

import ast
import difflib
from dataclasses import dataclass, field

from chaos_doctor.recipes import DECORATOR_ORDER, RECIPES

IMPORT_LINE = "from chaos_doctor import guards"


@dataclass
class FunctionInfo:
    name: str
    lineno: int
    calls_llm: bool
    calls: list[str]
    guards: list[str]
    doc: str
    guard_code: list[str] = field(default_factory=list)  # e.g. "@guards.retry(attempts=4, ...)"


def _guard_name(dec: ast.expr) -> str | None:
    node = dec.func if isinstance(dec, ast.Call) else dec
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        if node.value.id == "guards":
            return node.attr
    return None


def list_functions(source: str) -> list[FunctionInfo]:
    tree = ast.parse(source)
    out = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        calls = sorted(
            {
                n.func.id
                for n in ast.walk(node)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            }
        )
        segment = ast.get_source_segment(source, node) or ""
        out.append(
            FunctionInfo(
                name=node.name,
                lineno=node.lineno,
                calls_llm="chat.completions.create" in segment,
                calls=calls,
                guards=[g for g in (_guard_name(d) for d in node.decorator_list) if g],
                doc=(ast.get_docstring(node) or "").split("\n")[0],
                guard_code=[
                    "@" + (ast.get_source_segment(source, d) or "")
                    for d in node.decorator_list
                    if _guard_name(d)
                ],
            )
        )
    return out


def apply_recipe(source: str, function: str, recipe_name: str, params: dict) -> str:
    recipe = RECIPES[recipe_name]
    params = recipe.clean_params(params)
    tree = ast.parse(source)
    target = next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function), None
    )
    if target is None:
        raise ValueError(f"No top-level function named {function!r}")

    lines = source.splitlines(keepends=True)
    start = (target.decorator_list[0].lineno if target.decorator_list else target.lineno) - 1
    def_line = target.lineno - 1
    indent = lines[def_line][: len(lines[def_line]) - len(lines[def_line].lstrip())]

    # Keep non-guard decorators; rebuild the guard stack in a fixed, safe order.
    keep, stack = [], {}
    for dec in target.decorator_list:
        name = _guard_name(dec)
        text = ast.get_source_segment(source, dec) or ""
        if name:
            stack[name] = f"{indent}@{text}\n"
        else:
            keep.append(f"{indent}@{text}\n")
    stack[recipe_name] = f"{indent}{recipe.decorator(params)}\n"
    ordered = [stack[n] for n in DECORATOR_ORDER if n in stack]
    new_lines = lines[:start] + keep + ordered + lines[def_line:]
    new_source = "".join(new_lines)

    if IMPORT_LINE not in new_source:
        new_source = _add_import(new_source)
    ast.parse(new_source)  # guarantee we never write broken code
    return new_source


def _add_import(source: str) -> str:
    tree = ast.parse(source)
    imports = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    lines = source.splitlines(keepends=True)
    if imports:
        at = imports[-1].end_lineno or imports[-1].lineno
    elif (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(getattr(tree.body[0], "value", None), ast.Constant)
    ):
        at = tree.body[0].end_lineno or 1
    else:
        at = 0
    return "".join(lines[:at] + [IMPORT_LINE + "\n"] + lines[at:])


def diff(old: str, new: str, filename: str = "agent.py") -> str:
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
        )
    )

"""The demo site rebuilds the agent's code by applying each kept patch from a battle log to the
real demo agent. This checks every recorded battle still applies cleanly, using the same
algorithm as site/app.js (applyDiff)."""

import ast
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
AGENT = ROOT / "examples" / "shop_agent" / "agent.py"
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def apply_diff(lines: list[str], diff: str) -> list[str]:
    out, i = [], 0
    rows = diff.split("\n")
    k = 0
    while k < len(rows):
        m = HUNK.match(rows[k])
        k += 1
        if not m:
            continue
        old_start, old_len = int(m.group(1)), int(m.group(2) or 1)
        start = old_start - 1 if old_len else old_start
        out += lines[i:start]
        i = start
        while k < len(rows) and not rows[k].startswith("@@"):
            row = rows[k]
            k += 1
            if row.startswith("+") and not row.startswith("+++"):
                out.append(row[1:])
            elif row.startswith("-") and not row.startswith("---"):
                assert lines[i] == row[1:], f"removed line mismatch at {i + 1}"
                i += 1
            elif row.startswith(" "):
                assert lines[i] == row[1:], f"context mismatch at {i + 1}: {lines[i]!r}"
                out.append(lines[i])
                i += 1
    return out + lines[i:]


@pytest.mark.parametrize(
    "battle", sorted((ROOT / "site" / "battles").glob("*.json")), ids=lambda p: p.stem
)
def test_recorded_patches_apply_to_the_demo_agent(battle):
    lines = AGENT.read_text().split("\n")
    kept = [
        e for e in json.loads(battle.read_text())["events"] if e["kind"] == "patch" and e["kept"]
    ]
    assert kept
    for patch in kept:
        lines = apply_diff(lines, patch["diff"])
    final = "\n".join(lines)
    ast.parse(final)
    assert "@guards.retry" in final and "@guards.sanitize" in final

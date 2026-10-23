"""Doctor accuracy benchmark: 20 planted weaknesses, one diagnosis each.

    python benchmark/run.py --rules                 # rule-based baseline
    python benchmark/run.py --model qwen3:4b        # an open-weight model via Ollama
    python benchmark/run.py --report                # rebuild benchmark/RESULTS.md

For each case: copy an agent, plant the weakness, confirm the attack breaks it, ask the
Doctor for a diagnosis, apply the patch, and re-run the attack. A case counts as fixed only
if the attack fully passes afterwards.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chaos_doctor import doctor  # noqa: E402
from chaos_doctor.attacks import Attack  # noqa: E402
from chaos_doctor.config import load_settings  # noqa: E402
from chaos_doctor.llm import OllamaJSON  # noqa: E402
from chaos_doctor.patcher import apply_recipe  # noqa: E402
from chaos_doctor.scan import load_agent, run_attack  # noqa: E402

RESULTS = Path(__file__).parent / "results"

# name -> (agent file, tool, function that calls the tool, function that calls the model)
AGENTS = {
    "shop": (ROOT / "examples/shop_agent/agent.py", "lookup_order", "get_order", "ask_llm"),
    "helpdesk": (
        Path(__file__).parent / "agents/helpdesk/agent.py",
        "fetch_ticket",
        "load_ticket",
        "complete",
    ),
    "travel": (
        Path(__file__).parent / "agents/travel/agent.py",
        "flight_status_api",
        "lookup_flight",
        "generate_reply",
    ),
}

# attack kind -> (where the fix belongs, recipes that are a right answer)
EXPECTED = {
    "token_timeout": ("llm", {"retry"}),
    "rate_limit_storm": ("llm", {"retry"}),
    "silent_degradation": ("llm", {"validate_output"}),
    "context_length": ("llm", {"retry", "trim_prompt"}),
    "tool_failure": ("tool", {"retry", "fallback"}),
    "prompt_injection": ("tool", {"sanitize"}),
}


@dataclass
class Case:
    id: str
    agent: str
    attack: Attack
    pre_guard: tuple[str, str, dict] | None = None  # (function, recipe, params) planted first


def cases() -> list[Case]:
    out = []
    for name, (_, tool, _, _) in AGENTS.items():
        for kind in EXPECTED:
            target = tool if kind in ("tool_failure", "prompt_injection") else "llm"
            params = {"burst_count": 2} if kind == "rate_limit_storm" else {"fails": 1}
            out.append(Case(f"{name}/{kind}", name, Attack(kind, target, params)))
    # Strengthen cases: the right guard is there but too weak for this attack.
    out.append(
        Case(
            "shop/rate_limit_storm+weak_retry",
            "shop",
            Attack("rate_limit_storm", "llm", {"burst_count": 4}),
            ("ask_llm", "retry", {"attempts": 2}),
        )
    )
    out.append(
        Case(
            "travel/silent_degradation+weak_validate",
            "travel",
            Attack("silent_degradation", "llm", {"fails": 2}),
            ("generate_reply", "validate_output", {"retries": 1}),
        )
    )
    return out


@dataclass
class Outcome:
    case: str
    recipe: str
    params: dict
    function: str
    model_function: str
    expected_function: str
    function_correct: bool
    recipe_correct: bool
    placement_corrected: bool
    used_rules: bool
    fixed: bool
    seconds: float
    root_cause: str


def run_case(case: Case, llm) -> Outcome:
    agent_path, tool, tool_caller, llm_fn = AGENTS[case.agent]
    where, recipes = EXPECTED[case.attack.kind]
    expected_fn = llm_fn if where == "llm" else tool_caller
    with tempfile.TemporaryDirectory() as tmp:
        work_dir = Path(tmp) / case.agent
        shutil.copytree(agent_path.parent, work_dir, ignore=shutil.ignore_patterns("__pycache__"))
        work = work_dir / agent_path.name
        if case.pre_guard:
            fn, recipe, params = case.pre_guard
            work.write_text(apply_recipe(work.read_text(), fn, recipe, params))
        before = run_attack(load_agent(work), case.attack, trials=1)
        assert before.passes == 0, f"{case.id}: planted weakness did not fail"
        source = work.read_text()
        start = time.perf_counter()
        diag = doctor.diagnose(llm, source, before)
        seconds = time.perf_counter() - start
        corrected = re.match(r"\(placement corrected from (\w+)\(\)", diag.explanation)
        model_fn = corrected.group(1) if corrected else diag.target_function
        work.write_text(apply_recipe(source, diag.target_function, diag.recipe, diag.params))
        after = run_attack(load_agent(work), case.attack, trials=1)
    used_rules = diag.source == "rules"
    return Outcome(
        case=case.id,
        recipe=diag.recipe,
        params=diag.params,
        function=diag.target_function,
        model_function=model_fn,
        expected_function=expected_fn,
        function_correct=model_fn == expected_fn and not used_rules,
        recipe_correct=diag.recipe in recipes and not (used_rules and llm is not None),
        placement_corrected=bool(corrected),
        used_rules=used_rules,
        fixed=after.passes == after.trials,
        seconds=round(seconds, 1),
        root_cause=diag.root_cause,
    )


def summarise(name: str, rows: list[dict]) -> dict:
    n = len(rows)
    return {
        "doctor": name,
        "cases": n,
        "fixed": sum(r["fixed"] for r in rows),
        "function_correct": sum(r["function_correct"] for r in rows),
        "recipe_correct": sum(r["recipe_correct"] for r in rows),
        "placement_corrected": sum(r["placement_corrected"] for r in rows),
        "fell_back_to_rules": sum(r["used_rules"] for r in rows),
        "avg_seconds": round(sum(r["seconds"] for r in rows) / max(n, 1), 1),
    }


def report() -> None:
    files = sorted(RESULTS.glob("*.json"))
    lines = [
        "# Doctor benchmark results",
        "",
        "20 planted weaknesses across 3 agents (shop, helpdesk, travel). Each case: the attack "
        "breaks the agent, the Doctor diagnoses it once, the patch is applied, the attack is "
        "re-run. Reproduce with `python benchmark/run.py --model <ollama model>`.",
        "",
        "| Doctor | Fixed | Right function (model's own pick) | Right recipe | "
        "Placement corrected | Fell back to rules | Avg time per diagnosis |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for f in files:
        data = json.loads(f.read_text())
        s = data["summary"]
        n = s["cases"]
        model_cols = (
            ("n/a", "n/a", "n/a", "n/a")
            if s["doctor"] == "rules"
            else (
                f"{s['function_correct']}/{n}",
                f"{s['recipe_correct']}/{n}",
                f"{s['placement_corrected']}",
                f"{s['fell_back_to_rules']}",
            )
        )
        lines.append(
            f"| {s['doctor']} | **{s['fixed']}/{n}** | {model_cols[0]} | {model_cols[1]} | "
            f"{model_cols[2]} | {model_cols[3]} | {s['avg_seconds']} s |"
        )
    where = []
    for f in files:
        data = json.loads(f.read_text())
        where.append(f"{data['summary']['doctor']} ({data['hardware']})")
    lines += [
        "",
        "Recorded on: " + ", ".join(where) + ".",
        "",
        "The rule-based Doctor was written for this recipe menu, so 20/20 is its ceiling, not a "
        "fair rival; the model rows are the real test. Both qwen3:4b misses are "
        "`rate_limit_storm` on the shop agent: the model chose the right recipe (`retry`) on the "
        "right function, but the patch did not survive the 429 burst. This run predates "
        "parameter logging, so the cause (most likely too few attempts) is not recorded. A partial "
        "second run (stopped at case 14 when Ollama exited) reproduced the first miss and matched "
        "every other result.",
        "",
        "## Per case",
        "",
    ]
    for f in files:
        data = json.loads(f.read_text())
        lines += [
            f"### {data['summary']['doctor']}",
            "",
            "| Case | Fix | Params | On | Fixed |",
            "| --- | --- | --- | --- | --- |",
        ]
        for r in data["rows"]:
            on = r["function"] + ("()*" if r["placement_corrected"] else "()")
            if "params" not in r:
                params = "not recorded"  # results from before params were logged
            else:
                params = ", ".join(f"{k}={v}" for k, v in r["params"].items()) or "defaults"
            lines.append(
                f"| `{r['case']}` | `{r['recipe']}` | {params} | `{on}` | "
                f"{'yes' if r['fixed'] else 'no'} |"
            )
        lines.append("")
    lines.append(
        "\\* placement corrected by the call-site check (the model picked another function)."
    )
    (Path(__file__).parent / "RESULTS.md").write_text("\n".join(lines) + "\n")
    print("wrote benchmark/RESULTS.md")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="Ollama model for the Doctor, e.g. qwen3:4b")
    ap.add_argument("--rules", action="store_true", help="Rule-based Doctor (no model)")
    ap.add_argument("--report", action="store_true", help="Only rebuild RESULTS.md")
    ap.add_argument("--hardware", default="", help="Where it ran, for the results table")
    args = ap.parse_args()
    if args.report:
        return report()
    if not (args.model or args.rules):
        ap.error("pass --model NAME or --rules")
    llm = None
    name = "rules"
    if args.model:
        import os

        os.environ["CHAOS_DOCTOR_MODEL"] = args.model
        llm, name = OllamaJSON(load_settings()), args.model
    rows = []
    for case in cases():
        out = run_case(case, llm)
        rows.append(asdict(out))
        mark = "fixed" if out.fixed else "NOT fixed"
        print(
            f"{case.id:42} {out.recipe:16} {out.function + '()':18} {mark:9} {out.seconds:5.1f}s",
            flush=True,
        )
    summary = summarise(name, rows)
    RESULTS.mkdir(exist_ok=True)
    out_file = RESULTS / f"{name.replace(':', '-')}.json"
    out_file.write_text(
        json.dumps(
            {"summary": summary, "hardware": args.hardware or "local", "rows": rows}, indent=2
        )
    )
    print(json.dumps(summary, indent=2))
    report()


if __name__ == "__main__":
    main()

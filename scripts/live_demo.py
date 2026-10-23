"""Live, presenter-paced demo of a real Chaos Doctor battle, for judges.

    python scripts/live_demo.py                    # real model (default: CHAOS_DOCTOR_MODEL)
    python scripts/live_demo.py --model qwen3:4b   # pick the model
    python scripts/live_demo.py --offline          # no model: rule-based Doctor + Attacker
    python scripts/live_demo.py --no-pause         # run straight through

Every step prints what is about to happen in plain words, runs it for real on a copy of the
demo agent, shows the result, then waits for Enter so the presenter can explain it.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import httpx  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.rule import Rule  # noqa: E402
from rich.syntax import Syntax  # noqa: E402
from rich.table import Table  # noqa: E402

from chaos_doctor import attacker, doctor  # noqa: E402
from chaos_doctor.attacks import standard_attacks  # noqa: E402
from chaos_doctor.battle import heal  # noqa: E402
from chaos_doctor.config import load_settings  # noqa: E402
from chaos_doctor.llm import OllamaJSON  # noqa: E402
from chaos_doctor.patcher import apply_recipe, diff  # noqa: E402
from chaos_doctor.scan import ScanResult, load_agent, scan  # noqa: E402

console = Console()
PLAIN = {
    "token_timeout": "the model froze and timed out",
    "rate_limit_storm": "the provider sent a burst of 429 'too many requests' errors",
    "tool_failure": "the order-lookup tool crashed",
    "silent_degradation": "the model replied with scrambled text, no error",
    "context_length": "the model rejected the prompt as too long",
    "prompt_injection": "hidden text in the order data tried to hijack the agent",
}


def pause(enabled: bool, what: str = "continue") -> None:
    if enabled:
        console.input(f"\n[dim]⏎  Press Enter to {what}…[/]")


def step(n: int, title: str, say: str) -> None:
    console.print()
    console.print(Rule(f"[bold]Step {n} · {title}[/]", style="cyan"))
    console.print(f"[italic]{say}[/]\n")


def show_scan(result: ScanResult, title: str) -> None:
    table = Table(title=title, title_justify="left", expand=False)
    table.add_column("Attack", style="bold")
    table.add_column("What happened")
    table.add_column("Survived", justify="center")
    for r in result.results:
        ok = r.passes == r.trials
        table.add_row(
            r.attack.label,
            PLAIN.get(r.attack.kind, r.attack.kind),
            "[green]✓ yes[/]" if ok else "[red]✗ no[/]",
        )
    console.print(table)
    s = result.score
    color = "green" if s >= 90 else "yellow" if s >= 60 else "red"
    console.print(f"Resilience score: [bold {color}]{s}/100[/]")


def think(label: str, fn, *args):
    start = time.perf_counter()
    with console.status(f"{label} [dim](the model is thinking, usually 20-60 s on a laptop)[/]"):
        out = fn(*args)
    console.print(f"[dim]  answered in {time.perf_counter() - start:.0f} s[/]")
    return out


def model_ready(url: str, model: str) -> bool:
    try:
        tags = httpx.get(f"{url}/api/tags", timeout=5).json()
    except (httpx.HTTPError, ValueError):
        console.print(f"[yellow]Ollama is not reachable at {url}.[/]")
        return False
    names = [m["name"] for m in tags.get("models", [])]
    if model not in names:
        console.print(
            f"[yellow]Model {model} is not pulled on {url} (have: {', '.join(names)}).[/]"
        )
        return False
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--model", help="Ollama model, e.g. qwen3:4b or qwen3:8b")
    ap.add_argument("--offline", action="store_true", help="Rule-based Doctor and Attacker")
    ap.add_argument("--no-pause", action="store_true", help="Do not wait for Enter")
    args = ap.parse_args()
    if args.model:
        os.environ["CHAOS_DOCTOR_MODEL"] = args.model
    settings = load_settings()
    paused = not args.no_pause

    llm, who = None, "rule-based Doctor (no model)"
    if not args.offline:
        if model_ready(settings.ollama_url, settings.model):
            llm, who = OllamaJSON(settings), f"{settings.model} via Ollama, running locally"
        else:
            console.print(
                "[yellow]Falling back to the rule-based Doctor so the demo keeps going.[/]"
            )

    work_dir = ROOT / ".chaos-doctor" / f"live-{datetime.now():%H%M%S}"
    shutil.copytree(
        ROOT / "examples" / "shop_agent", work_dir, ignore=shutil.ignore_patterns("__pycache__")
    )
    agent = work_dir / "agent.py"
    tools = list(load_agent(agent).TOOLS)
    history: list[int] = []

    console.print(
        Panel.fit(
            "[bold]Chaos Doctor · live battle[/]\n"
            "Two open-weight AIs fight over an agent: one attacks it, one heals it.\n\n"
            f"Doctor + Attacker: [bold]{who}[/]\n"
            f"Faults and judging: [bold]agentic-chaos[/] (DeepAgentLabs)\n"
            f"Working copy: {work_dir.relative_to(ROOT)}",
            border_style="green",
        )
    )
    pause(paused, "meet the agent")

    # 1. the agent
    step(
        1,
        "Meet the agent",
        "A shop support bot. It looks up an order with a tool, then asks "
        "an LLM to write the reply. Notice: no retries, no timeouts, no input checks.",
    )
    src = agent.read_text()
    start = src.index("def get_order")
    end = src.index("def run")
    console.print(Syntax(src[start:end].rstrip(), "python", theme="monokai", line_numbers=False))
    pause(paused, "attack it")

    # 2. attack
    step(
        2,
        "Attack",
        "agentic-chaos now injects the five failures that hit real agents in "
        "production, and judges every run with its contracts plus the agent's own answer check.",
    )
    attacks = standard_attacks(tools)
    result = scan(agent, attacks, trials=1)
    show_scan(result, "Round 1 · five classic failures")
    history.append(result.score)
    pause(paused, "call the Doctor")

    # 3. diagnose one failure in detail
    worst = result.failing[0]
    step(
        3,
        "Diagnose",
        f"The Doctor gets the failure ({PLAIN[worst.attack.kind]}) and the "
        "source code, and must answer in strict JSON from a fixed menu of fixes.",
    )
    diag = think(
        "Doctor AI is reading the failure…", doctor.diagnose, llm, agent.read_text(), worst
    )
    console.print(
        Panel(
            Syntax(json.dumps(diag.to_dict(), indent=2), "json", theme="monokai"),
            title=f"Doctor's prescription ({'AI' if diag.source == 'llm' else 'rules'})",
            border_style="green",
        )
    )
    pause(paused, "apply the fix")

    # 4. patch + verify
    step(
        4,
        "Patch and verify",
        "Python's ast adds one guard decorator, so the code always "
        "parses. Then every attack runs again.",
    )
    before_src = agent.read_text()
    agent.write_text(apply_recipe(before_src, diag.target_function, diag.recipe, diag.params))
    console.print(Syntax(diff(before_src, agent.read_text(), "agent.py"), "diff", theme="monokai"))
    after = scan(agent, attacks, trials=1)
    console.print(f"\nScore: [bold]{result.score} → {after.score}[/]")
    if after.score <= result.score:
        agent.write_text(before_src)
        after = result
        console.print("[yellow]It didn't help, so it's rolled back. The Doctor will try again.[/]")
    result = after
    history.append(result.score)
    pause(paused, "let the Doctor heal the rest")

    # 5. heal the rest
    step(
        5,
        "Heal everything else",
        "The Doctor keeps going, one failure at a time. A patch is kept only if the score goes up.",
    )

    def emit(kind: str, data: dict) -> None:
        if kind == "diagnosis":
            tag = "AI" if data.get("source") == "llm" else "rules"
            console.print(
                f"[cyan]Doctor ({tag}):[/] {data['attack']} → "
                f"[bold]@guards.{data['recipe']}[/] on {data['target_function']}()"
            )
        elif kind == "patch":
            verdict = "[green]kept[/]" if data["kept"] else "[yellow]rolled back[/]"
            console.print(f"   score {data['before']} → {data['after']}: {verdict}")

    with console.status("Healing… [dim](one model call per failure)[/]"):
        result = heal(agent, attacks, result, llm, 1, emit)
    show_scan(result, "After healing")
    history.append(result.score)
    pause(paused, "hand it to the Attacker")

    # 6. attacker
    step(
        6,
        "The Attacker strikes back",
        "Now the Attacker AI reads the patched code and "
        "invents a new attack aimed at whatever is still unprotected.",
    )
    new = think(
        "Attacker AI is studying the patched code…",
        attacker.propose,
        llm,
        agent.read_text(),
        attacks,
        tools,
    )
    console.print(
        Panel(
            Syntax(json.dumps(new.to_dict(), indent=2), "json", theme="monokai"),
            title="Attacker's move",
            border_style="red",
        )
    )
    attacks = (
        attacks + [new]
        if new.label not in {a.label for a in attacks}
        else [new if a.label == new.label else a for a in attacks]
    )
    result = scan(agent, attacks, trials=1)
    show_scan(result, f"Round 2 · {new.label}")
    history.append(result.score)
    if result.failing:
        pause(paused, "let the Doctor respond")
        with console.status("Doctor is responding…"):
            result = heal(agent, attacks, result, llm, 1, emit)
        show_scan(result, "After healing again")
        history.append(result.score)

    # summary
    console.print()
    console.print(Rule("[bold green]Battle over[/]", style="green"))
    guards = [line.strip() for line in agent.read_text().splitlines() if "@guards." in line]
    console.print(f"Score history: [bold]{' → '.join(map(str, history))}[/]")
    console.print("Guards the Doctor added:\n  " + "\n  ".join(guards))
    console.print(f"\nPatched agent: {agent.relative_to(ROOT)}  ·  every change is a plain diff.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[dim]Demo stopped.[/]")

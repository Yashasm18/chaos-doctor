"""Command-line interface: scan, diagnose, fix, verify, battle."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from chaos_doctor import doctor
from chaos_doctor.attacks import standard_attacks
from chaos_doctor.battle import battle as run_battle
from chaos_doctor.config import load_settings
from chaos_doctor.llm import LLMError, OllamaJSON
from chaos_doctor.patcher import apply_recipe, diff
from chaos_doctor.scan import AgentContractError, ScanResult, load_agent, scan

app = typer.Typer(add_completion=False, help="Break your agent, find why, fix it, prove it.")
console = Console()
STATE = Path(".chaos-doctor")

AgentArg = typer.Argument(..., exists=True, dir_okay=False, help="Path to the agent .py file")
OfflineOpt = typer.Option(False, "--offline", help="Use the rule-based doctor, no model needed")
TrialsOpt = typer.Option(None, "--trials", help="Runs per attack (default from settings)")


def _llm(offline: bool):
    settings = load_settings()
    return (None if offline else OllamaJSON(settings)), settings


def _score_style(score: int) -> str:
    return "green" if score >= 90 else "yellow" if score >= 60 else "red"


def _print_scan(result: ScanResult, title: str) -> None:
    table = Table(title=title, show_lines=False)
    table.add_column("Attack")
    table.add_column("Passed", justify="right")
    table.add_column("First failure", overflow="fold")
    for r in result.results:
        ok = r.passes == r.trials
        table.add_row(
            r.attack.label,
            f"[{'green' if ok else 'red'}]{r.passes}/{r.trials}[/]",
            "" if ok else r.failures[0][:90],
        )
    console.print(table)
    s = result.score
    console.print(f"Resilience score: [bold {_score_style(s)}]{s}/100[/]\n")


def _save(name: str, data: dict[str, Any]) -> None:
    STATE.mkdir(exist_ok=True)
    (STATE / name).write_text(json.dumps(data, indent=2, default=str))


def _scan(agent: Path, trials: int | None) -> ScanResult:
    settings = load_settings()
    try:
        tools = list(load_agent(agent).TOOLS)
    except AgentContractError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(2) from exc
    with console.status("Injecting faults..."):
        return scan(agent, standard_attacks(tools), trials or settings.trials)


@app.command("scan")
def scan_cmd(
    agent: Path = AgentArg,
    trials: int = TrialsOpt,
    min_score: int = typer.Option(0, "--min-score", help="Exit 1 if the score is lower (CI gate)"),
) -> None:
    """Attack the agent with the 5 standard faults and print its resilience score."""
    result = _scan(agent, trials)
    _print_scan(result, f"Chaos scan: {agent.name}")
    _save("last_scan.json", result.to_dict())
    if result.score < min_score:
        console.print(f"[red]Score {result.score} is below the gate of {min_score}.[/]")
        raise typer.Exit(1)


def _diagnose(agent: Path, offline: bool, trials: int | None):
    result = _scan(agent, trials)
    _print_scan(result, f"Chaos scan: {agent.name}")
    if not result.failing:
        console.print("[green]Nothing failed. No diagnosis needed.[/]")
        raise typer.Exit(0)
    llm, settings = _llm(offline)
    who = "rules" if offline else settings.model
    with console.status(f"Doctor ({who}) is reading the failure..."):
        try:
            diag = doctor.diagnose(llm, agent.read_text(), result.failing[0])
        except LLMError as exc:
            console.print(f"[red]{exc}[/]\nTip: run with --offline to use the rule-based doctor.")
            raise typer.Exit(2) from exc
    console.print(
        Panel(
            f"[bold]Attack:[/] {result.failing[0].attack.label}\n"
            f"[bold]Root cause:[/] {diag.root_cause}\n"
            f"[bold]Fix:[/] {diag.recipe}{diag.params} on {diag.target_function}()\n"
            f"[bold]Confidence:[/] {diag.confidence:.2f}\n\n{diag.explanation}",
            title=f"Diagnosis ({diag.source})",
        )
    )
    return result, diag


@app.command("diagnose")
def diagnose_cmd(agent: Path = AgentArg, offline: bool = OfflineOpt, trials: int = TrialsOpt):
    """Scan, then let the Doctor explain the worst failure."""
    _, diag = _diagnose(agent, offline, trials)
    _save("last_diagnosis.json", diag.to_dict())


@app.command("fix")
def fix_cmd(
    agent: Path = AgentArg,
    offline: bool = OfflineOpt,
    trials: int = TrialsOpt,
    apply: bool = typer.Option(False, "--apply", help="Write the patch to the agent file"),
):
    """Diagnose the worst failure and propose a patch (written only with --apply)."""
    before, diag = _diagnose(agent, offline, trials)
    source = agent.read_text()
    patched = apply_recipe(source, diag.target_function, diag.recipe, diag.params)
    console.print(Syntax(diff(source, patched, agent.name), "diff", theme="ansi_dark"))
    if not apply:
        console.print("Dry run. Re-run with [bold]--apply[/] to write this patch.")
        return
    STATE.mkdir(exist_ok=True)
    backup = STATE / f"{agent.stem}.{datetime.now():%H%M%S}.bak.py"
    backup.write_text(source)
    agent.write_text(patched)
    _save("baseline.json", before.to_dict())
    console.print(f"Patched {agent} (backup: {backup}). Run [bold]verify[/] to prove it.")


@app.command("verify")
def verify_cmd(agent: Path = AgentArg, trials: int = TrialsOpt):
    """Re-scan and compare with the score saved before the last fix."""
    result = _scan(agent, trials)
    _print_scan(result, f"Verify: {agent.name}")
    base_file = STATE / "baseline.json"
    if base_file.exists():
        before = json.loads(base_file.read_text())["score"]
        delta = result.score - before
        console.print(f"[bold]Resilience: {before} -> {result.score} ({delta:+d})[/]")


@app.command("battle")
def battle_cmd(
    agent: Path = AgentArg,
    offline: bool = OfflineOpt,
    trials: int = TrialsOpt,
    rounds: int = typer.Option(None, "--rounds", help="Max rounds (default from settings)"),
    out: Path = typer.Option(None, "--out", help="Output folder for the patched agent + log"),
):
    """Attacker vs Doctor, round after round, until the agent is battle-tested."""
    llm, settings = _llm(offline)
    out = out or STATE / f"battle-{datetime.now():%Y%m%d-%H%M%S}"
    who = "rules (offline)" if offline else settings.model

    def show(kind: str, data: dict[str, Any]) -> None:
        if kind == "round":
            console.rule(f"[bold]Round {data['round']}[/]")
            if "new_attack" in data:
                a = data["new_attack"]
                console.print(
                    f"[magenta]Attacker:[/] {a['kind']} on {a['target']} {a['params']}\n"
                    f"  [dim]{a.get('rationale', '')}[/]"
                )
        elif kind == "scan":
            s = data["score"]
            console.print(f"{data['phase'].title()}: [bold {_score_style(s)}]{s}/100[/]")
        elif kind == "diagnosis":
            console.print(
                f"[cyan]Doctor:[/] {data['attack']} -> {data['recipe']} on "
                f"{data['target_function']}()  [dim]{data['root_cause']}[/]"
            )
        elif kind == "patch":
            verdict = "[green]kept[/]" if data["kept"] else "[red]rolled back[/]"
            console.print(f"  patch {data['before']} -> {data['after']}: {verdict}")
        elif kind == "done":
            console.rule(f"Final score: {data['final_score']}/100")
            console.print(f"Patched agent: {data['patched_agent']}")

    console.print(
        Panel(f"Agent: {agent}\nModel: {who}\nOutput: {out}", title="Chaos Doctor battle")
    )
    try:
        log = run_battle(
            agent,
            out,
            llm,
            settings.model,
            trials=trials or settings.trials,
            max_rounds=rounds or settings.max_rounds,
            target=settings.target_score,
            emit=show,
        )
    except LLMError as exc:
        console.print(f"[red]{exc}[/]\nTip: run with --offline to use the rule-based doctor.")
        raise typer.Exit(2) from exc
    scores = " -> ".join(str(s["score"]) for s in log.scores)
    console.print(f"Score history: {scores}\nLog: {out / 'battle.json'}")


if __name__ == "__main__":
    app()

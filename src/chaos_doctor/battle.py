"""The battle loop: Attacker invents attacks, Doctor patches, the scanner keeps score."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chaos_doctor import attacker, doctor
from chaos_doctor.attacks import Attack, standard_attacks
from chaos_doctor.llm import JsonLLM
from chaos_doctor.patcher import apply_recipe, diff
from chaos_doctor.scan import ScanResult, load_agent, scan

Event = Callable[[str, dict[str, Any]], None]


@dataclass
class BattleLog:
    agent: str
    model: str
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    events: list[dict[str, Any]] = field(default_factory=list)
    scores: list[dict[str, Any]] = field(default_factory=list)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.__dict__, indent=2, default=str))


def heal(
    work: Path,
    attacks: list[Attack],
    result: ScanResult,
    llm: JsonLLM | None,
    trials: int,
    emit: Event,
    max_fixes: int = 5,
) -> ScanResult:
    """Let the Doctor fix failing attacks one at a time, keeping only patches that help."""
    stuck: set[str] = set()  # attacks whose fix didn't change or didn't help this round
    for _ in range(max_fixes):
        failing = [r for r in result.failing if r.attack.label not in stuck]
        if not failing:
            break
        worst = failing[0]
        source = work.read_text()
        diag = doctor.diagnose(llm, source, worst)
        emit("diagnosis", {"attack": worst.attack.label, **diag.to_dict()})
        try:
            patched = apply_recipe(source, diag.target_function, diag.recipe, diag.params)
        except ValueError as exc:
            emit("patch_error", {"attack": worst.attack.label, "error": str(exc)})
            stuck.add(worst.attack.label)
            continue
        if patched == source and diag.source == "llm":
            # The model re-picked a guard that's already there as-is; strengthen it instead.
            diag = doctor.rule_based(source, worst)
            emit("diagnosis", {"attack": worst.attack.label, **diag.to_dict()})
            patched = apply_recipe(source, diag.target_function, diag.recipe, diag.params)
        if patched == source:
            emit("patch_noop", {"attack": worst.attack.label})
            stuck.add(worst.attack.label)
            continue
        work.write_text(patched)
        new = scan(work, attacks, trials)
        kept = new.score > result.score  # a patch must earn its place
        emit(
            "patch",
            {
                "attack": worst.attack.label,
                "recipe": diag.recipe,
                "function": diag.target_function,
                "diff": diff(source, patched, work.name),
                "before": result.score,
                "after": new.score,
                "kept": kept,
            },
        )
        if kept:
            result = new
        else:
            work.write_text(source)
            stuck.add(worst.attack.label)
    return result


def battle(
    agent_path: Path,
    out_dir: Path,
    llm: JsonLLM | None,
    model_name: str,
    trials: int = 3,
    max_rounds: int = 5,
    target: int = 90,
    emit: Event | None = None,
) -> BattleLog:
    # Work on a copy of the agent's folder (it may load data files next to itself).
    shutil.copytree(
        agent_path.parent,
        out_dir,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", ".chaos-doctor*"),
    )
    work = out_dir / agent_path.name
    log = BattleLog(agent=str(agent_path), model=model_name if llm else "rules (offline)")

    def record(kind: str, data: dict[str, Any]) -> None:
        log.events.append({"kind": kind, "t": datetime.now(timezone.utc).isoformat(), **data})
        log.save(out_dir / "battle.json")
        if emit:
            emit(kind, data)

    tools = list(load_agent(work).TOOLS)
    attacks = standard_attacks(tools)
    result = scan(work, attacks, trials)
    record("round", {"round": 1, "attacks": [a.to_dict() for a in attacks]})
    record("scan", {"round": 1, "phase": "attacked", **result.to_dict()})
    log.scores.append({"round": 1, "phase": "attacked", "score": result.score})

    for rnd in range(1, max_rounds + 1):
        if rnd > 1:
            new_attack = attacker.propose(llm, work.read_text(), attacks, tools)
            if any(
                a.to_dict() | {"rationale": ""} == new_attack.to_dict() | {"rationale": ""}
                for a in attacks
            ):
                # An exact repeat teaches nothing; take the next untried or harder attack.
                new_attack = attacker.fallback_attack(attacks, tools)
            labels = [a.label for a in attacks]
            if new_attack.label in labels:
                attacks[labels.index(new_attack.label)] = new_attack  # a harder variant
            else:
                attacks.append(new_attack)
            record("round", {"round": rnd, "new_attack": new_attack.to_dict()})
            result = scan(work, attacks, trials)
            record("scan", {"round": rnd, "phase": "attacked", **result.to_dict()})
            log.scores.append({"round": rnd, "phase": "attacked", "score": result.score})

        result = heal(work, attacks, result, llm, trials, record)
        record("scan", {"round": rnd, "phase": "healed", **result.to_dict()})
        log.scores.append({"round": rnd, "phase": "healed", "score": result.score})
        # Give the Attacker at least two tries before declaring the agent battle-tested.
        if rnd >= 3 and result.score >= target:
            break

    record("done", {"final_score": result.score, "patched_agent": str(work)})
    return log

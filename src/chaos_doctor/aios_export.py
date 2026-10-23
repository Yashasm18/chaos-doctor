"""Export scans as AI Operations Spec (AIOS) v0.4-draft Run artifacts.

Each trial becomes one AIOS Run, built by agentic-chaos's own exporter (which follows the
spec's reviewed agentic-chaos mapping). Chaos Doctor adds what it knows on top, in its own
reverse-domain extension: which attack it was, the verdict, the score, and where the run sits
in a battle. That makes every battle readable by any AIOS consumer in the DeepAgentLabs
ecosystem (AgenticLens, Control Tower).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agentic_chaos.export.aios import to_aios_run

from chaos_doctor import __version__
from chaos_doctor.scan import ScanResult

EXTENSION = "io.github.yashasm18.chaos-doctor"


def scan_to_runs(result: ScanResult, context: dict[str, Any] | None = None) -> list[dict]:
    """One AIOS Run per trial of every attack in this scan."""
    runs = []
    for attack_result in result.results:
        for trial, (report, reason) in enumerate(attack_result.trial_reports):
            status = "failed" if report.unhandled_error else "completed"
            run = to_aios_run(report, status=status, producer_version=__version__)
            run.setdefault("extensions", {})[EXTENSION] = {
                "producer_version": __version__,
                "attack": attack_result.attack.to_dict(),
                "attack_label": attack_result.attack.label,
                "trial": trial,
                "verdict": "passed" if reason is None else "failed",
                "failure": reason,
                "scan_score": result.score,
                **(context or {}),
            }
            runs.append(run)
    return runs


def write_runs(runs: list[dict], out_dir: Path, prefix: str = "") -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, run in enumerate(runs):
        label = run["extensions"][EXTENSION]["attack_label"]
        safe = re.sub(r"[^a-z0-9_-]+", "-", label.lower()).strip("-")
        path = out_dir / f"{prefix}{i:03d}-{safe}.aios.json"
        path.write_text(json.dumps(run, indent=2, default=str))
        paths.append(path)
    return paths

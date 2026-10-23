"""Vercel Python function: run a fresh offline battle and return its log as JSON.

POST /api/battle -> battle.json (rule-based Doctor and Attacker, simulated victim model).
No model runs in the cloud; the recorded real-model battle is served as a static file.
"""

import json
import sys
import tempfile
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chaos_doctor.battle import battle  # noqa: E402

AGENT = ROOT / "examples" / "shop_agent" / "agent.py"


def run() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        log = battle(AGENT, Path(tmp) / "run", llm=None, model_name="rules", trials=2, max_rounds=4)
    data = dict(log.__dict__)
    data["agent"] = "examples/shop_agent/agent.py"
    for ev in data["events"]:
        if ev.get("kind") == "done":
            ev["patched_agent"] = "agent.py (patched copy)"
    return data


class handler(BaseHTTPRequestHandler):  # noqa: N801 - Vercel looks for this name
    def _send(self, status: int, body: dict) -> None:
        raw = json.dumps(body, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:  # noqa: N802
        try:
            self._send(200, run())
        except Exception as exc:  # report, don't hang the demo
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

    def do_GET(self) -> None:  # noqa: N802
        self._send(405, {"error": "POST to run a battle"})

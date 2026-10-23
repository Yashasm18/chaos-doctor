"""Serve the demo site locally and stream a real battle to it, live.

    chaos-doctor live --model qwen3:8b

The page is the same site that runs on GitHub Pages. When it is served from here it also finds
/api/live/*, shows a "Live battle" tab, and replays events the moment the battle produces them,
including "thinking" while the Doctor or Attacker model is working. Standard library only.
"""

from __future__ import annotations

import json
import runpy
import threading
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from chaos_doctor.battle import battle
from chaos_doctor.config import Settings
from chaos_doctor.llm import OllamaJSON

REPO = Path(__file__).resolve().parents[2]
SITE = REPO / "site"
AGENT = REPO / "examples" / "shop_agent" / "agent.py"


class Live:
    """Shared settings and a lock so only one battle streams at a time."""

    def __init__(self, settings: Settings, offline: bool, trials: int, rounds: int) -> None:
        self.settings = settings
        self.offline = offline
        self.trials = trials
        self.rounds = rounds
        self.lock = threading.Lock()

    def model_status(self) -> dict[str, Any]:
        if self.offline:
            return {"ready": False, "reason": "offline mode"}
        try:
            tags = httpx.get(f"{self.settings.ollama_url}/api/tags", timeout=3).json()
        except (httpx.HTTPError, ValueError):
            return {"ready": False, "reason": f"Ollama not reachable at {self.settings.ollama_url}"}
        names = [m["name"] for m in tags.get("models", [])]
        if self.settings.model not in names:
            return {"ready": False, "reason": f"{self.settings.model} not pulled"}
        return {"ready": True}


class Handler(SimpleHTTPRequestHandler):
    live: Live

    def log_message(self, fmt: str, *args: Any) -> None:  # keep the terminal quiet
        if "/api/" in (args[0] if args else ""):
            super().log_message(fmt, *args)

    def _json(self, body: dict[str, Any], status: int = 200) -> None:
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _from_this_page(self) -> bool:
        """Only our own page may use the API: blocks other websites (CSRF) and DNS rebinding."""
        port = self.server.server_address[1]
        own = {f"localhost:{port}", f"127.0.0.1:{port}"}
        if self.headers.get("Host", "") not in own:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin.removeprefix("http://") in own

    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        if url.path.startswith("/api/") and not self._from_this_page():
            return self._json(
                {"error": "forbidden: only the local Chaos Doctor page may call this"}, 403
            )
        if url.path == "/api/live/health":
            status = self.live.model_status()
            return self._json({"live": True, "model": self.live.settings.model, **status})
        if url.path == "/api/live/start":
            return self._stream(parse_qs(url.query))
        return super().do_GET()

    def _send_event(self, data: dict[str, Any]) -> None:
        self.wfile.write(f"data: {json.dumps(data, default=str)}\n\n".encode())
        self.wfile.flush()

    def _stream(self, query: dict[str, list[str]]) -> None:
        if not self.live.lock.acquire(blocking=False):
            return self._json({"error": "a battle is already running"}, 409)
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            want_model = query.get("mode", ["model"])[0] != "offline"
            status = self.live.model_status()
            llm = OllamaJSON(self.live.settings) if want_model and status["ready"] else None
            model = self.live.settings.model if llm else "rules (offline)"
            started = datetime.now(timezone.utc).isoformat()
            self._send_event(
                {
                    "kind": "meta",
                    "model": model,
                    "started_at": started,
                    "note": None if llm or not want_model else status.get("reason"),
                }
            )
            out = REPO / ".chaos-doctor" / f"live-web-{datetime.now():%H%M%S}"

            def emit(kind: str, data: dict[str, Any]) -> None:
                self._send_event(
                    {"kind": kind, "t": datetime.now(timezone.utc).isoformat(), **data}
                )

            battle(
                AGENT,
                out,
                llm,
                self.live.settings.model,
                trials=self.live.trials,
                max_rounds=self.live.rounds,
                target=self.live.settings.target_score,
                emit=emit,
            )
            self._send_event({"kind": "end"})
        except (BrokenPipeError, ConnectionResetError):
            pass  # the browser left; stop quietly
        except Exception as exc:  # show it in the page instead of hanging the demo
            try:
                self._send_event({"kind": "error", "error": f"{type(exc).__name__}: {exc}"})
            except OSError:
                pass
        finally:
            self.live.lock.release()


def serve(settings: Settings, port: int, offline: bool, trials: int, rounds: int) -> str:
    if not SITE.exists():
        raise FileNotFoundError(f"Demo site not found at {SITE}; run from a clone of the repo.")
    runpy.run_path(str(REPO / "scripts" / "build_site.py"), run_name="__main__")
    Handler.live = Live(settings, offline, trials, rounds)
    handler = partial(Handler, directory=str(SITE))
    # Take the first free port, so a busy one never blocks a demo.
    for candidate in range(port, port + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", candidate), handler)
            break
        except OSError:
            continue
    else:
        raise OSError(f"No free port between {port} and {port + 19}")
    url = f"http://localhost:{candidate}/"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return url

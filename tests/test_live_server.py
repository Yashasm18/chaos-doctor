"""`chaos-doctor live`: the local server streams a real (offline) battle as server-sent events."""

import json

import httpx

from chaos_doctor.config import load_settings
from chaos_doctor.live_server import serve


def test_live_server_streams_a_battle():
    url = serve(load_settings(), port=18765, offline=True, trials=1, rounds=2)

    health = httpx.get(url + "api/live/health", timeout=5).json()
    assert health["live"] is True and health["ready"] is False  # offline mode

    assert httpx.get(url, timeout=5).status_code == 200  # the site itself
    assert httpx.get(url + "data/shop_agent.py.txt", timeout=5).status_code == 200

    events = []
    with httpx.stream("GET", url + "api/live/start?mode=offline", timeout=60) as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        for line in resp.iter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[6:])
                events.append(ev)
                if ev["kind"] in ("end", "error"):
                    break
    kinds = [e["kind"] for e in events]
    assert kinds[0] == "meta" and kinds[-1] == "end"
    assert {"round", "scan", "diagnosis", "patch", "done", "thinking"} <= set(kinds)
    assert next(e for e in events if e["kind"] == "done")["final_score"] == 100

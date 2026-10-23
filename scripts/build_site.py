"""Copy the data the demo site shows into site/data/ (run before serving or deploying).

The site replays battle logs against the real demo agent source, so it needs a copy of that
source, the flowchart, and the benchmark and leaderboard results. Keeping one source of truth in
the repo and copying at build time means the site can never drift from the code.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "data"


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    shutil.copy(ROOT / "examples/shop_agent/agent.py", OUT / "shop_agent.py.txt")
    shutil.copy(ROOT / "docs/images/how-it-works.svg", OUT / "how-it-works.svg")

    bench = {}
    for f in sorted((ROOT / "benchmark/results").glob("*.json")):
        data = json.loads(f.read_text())
        bench[data["summary"]["doctor"]] = data["summary"]
    leaderboard = {}
    for f in sorted((ROOT / "examples/leaderboard/results").glob("*.json")):
        scores = [s["score"] for s in json.loads(f.read_text())["scores"]]
        leaderboard[f.stem] = {"before": scores[0], "after": scores[-1]}
    (OUT / "results.json").write_text(
        json.dumps({"benchmark": bench, "leaderboard": leaderboard}, indent=2)
    )
    print(f"wrote {sorted(p.name for p in OUT.iterdir())} to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

# Live demo runbook

How to show judges a **real** Chaos Doctor battle, live, with an open-weight model running on
our own laptop. Target: about 5 minutes, plus questions.

## Roles (3 people)

| Role | Who does it | Job |
| --- | --- | --- |
| **Presenter** | the best speaker | Talks. Explains each step while the screen shows it. |
| **Driver** | owner of the laptop with Ollama | Runs `scripts/live_demo.py` and presses Enter when the presenter is ready. |
| **Backup** | the third person | Keeps the [demo site](https://yashasm18.github.io/chaos-doctor/) and the GitHub repo open on a second laptop, runs the `--offline` fallback if needed, answers code questions. |

## Before judging (do this by 5:15 PM)

On the **Driver's** laptop:

```bash
git pull                                   # latest main
pip install -e ".[dev]"                    # inside the .venv
ollama serve                               # leave running (Windows: the Ollama app in the tray)
ollama pull qwen3:8b                       # 16 GB RAM / GPU; use qwen3:4b on 8 GB laptops
ollama run qwen3:8b "say ready"            # warm-up: loads the model into memory once
```

Then a dry run, straight through:

```bash
python scripts/live_demo.py --model qwen3:8b --no-pause
```

Checklist:

- [ ] Dry run finished and ended with "Battle over" (note how long it took)
- [ ] Terminal font is large (Cmd/Ctrl and + a few times) and the window is full screen
- [ ] Other heavy apps are closed (the model needs the RAM)
- [ ] Laptop is charged and plugged in; Wi-Fi is not needed, everything is local
- [ ] Backup laptop has the demo site and the repo open
- [ ] Everyone is wearing their wristband

Windows (PowerShell) equivalents: `.venv\Scripts\Activate.ps1`, then
`python scripts\live_demo.py --model qwen3:8b`.

## The demo, step by step

Start it with pauses (the default):

```bash
python scripts/live_demo.py --model qwen3:8b
```

The script prints a heading and a one-line explanation for each step, does it for real, then
waits for Enter. What the presenter says:

| Step | On screen | Say (in your own words) |
| --- | --- | --- |
| Intro | Banner: model, agentic-chaos, working copy | "Agents break in production. Chaos Doctor breaks them on purpose, finds why with a local open-weight model, fixes the code and proves it with a score. Everything you see runs on this laptop, no cloud." |
| 1 · Meet the agent | `get_order` and `ask_llm` code | "A shop support bot. One tool call, one LLM call. No retries, no timeouts, no input checks, like most agent code." |
| 2 · Attack | Table of 5 attacks, all ✗, **score 0/100** | "agentic-chaos, from DeepAgentLabs, injects the five failures that hit real agents. Every one crashes or fools it. Score zero." |
| 3 · Diagnose | Spinner, then the Doctor's JSON | "Now the Doctor, Qwen3 running here, reads the failure and the code. It must answer in strict JSON and pick from a fixed menu of fixes. That's why a small model is reliable: it chooses, it doesn't free-write code." Point at `root_cause`, `recipe`, `target_function`. |
| 4 · Patch and verify | A diff with one `@guards...` line, score goes up | "The fix is one decorator added with Python's ast, so the code always parses. We re-test everything; the patch is kept only because the score went up." |
| 5 · Heal everything | One line per fix, then all ✓ | "It keeps going until every attack is survived." |
| 6 · Attacker strikes back | The Attacker's JSON (often a prompt injection), score drops, then heals | "Now the other AI reads the patched code and invents a new attack, here a prompt injection hidden in the order data. The Doctor answers it with an input sanitizer." |
| Battle over | Score history and the guards added | "From zero to battle-tested. Every change is a plain diff you can review." |

While a model is thinking (20-60 s), fill the time: explain the agent contract, the attack menu,
or show the repo on the backup laptop (tests, CI, the benchmark).

## Then show the proof (1 minute)

On the backup laptop:

1. **Benchmark:** `benchmark/RESULTS.md`: qwen3:4b fixed 18/20 planted bugs on its own.
2. **Open source:** green CI, the Agent Skill (`chaos-doctor/SKILL.md`, validated), AIOS export,
   issue → PR → review history.
3. **The demo site:** the arena replays a recorded battle step by step if they want to see it
   again at their own pace.

## If something goes wrong

| Problem | Do this |
| --- | --- |
| Ollama not running / model missing | The script says so and continues with the rule-based Doctor. Or start `ollama serve` and rerun. |
| The model is very slow | Ctrl+C, then `python scripts/live_demo.py --offline` (a few seconds). Say: "same loop, rule-based Doctor; the AI version is recorded on the site." |
| Laptop crashes or freezes | Backup laptop: the demo site's "Real AI battle" replay, presented with the arrow keys. |
| A judge asks "is it real?" | Open the working copy it printed (`.chaos-doctor/live-<time>/agent.py`) and show the guards in the file. |

## Questions judges may ask

- **Why trust a 4B/8B model to edit code?** It never writes free code. It picks one of six
  recipes and fills in parameters; an ast patcher makes the change, the file must parse, and the
  scan must improve or the patch is rolled back.
- **What does the AI do that rules can't?** It reads unfamiliar code and failures and decides
  where and how to fix them, and the Attacker invents new attacks. On the benchmark, the model's
  own choices fixed 18/20 bugs across three agents with different function names.
- **How does this use DeepAgentLabs?** agentic-chaos injects every fault and its contracts judge
  every run; battles export as AIOS v0.4 Runs (34/34 validate against the official schema).
- **Limitations?** Only the first model call site is attacked; agents that swallow errors into
  an apology can't be fixed by retry; the garbled-text check is an English word heuristic.

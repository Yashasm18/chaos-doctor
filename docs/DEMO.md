# Live demo runbook

How to show judges a **real** Chaos Doctor battle, live, with an open-weight model running on
our own laptop. Target: about 5 minutes, plus questions.

## Roles (3 people)

| Role | Who does it | Job |
| --- | --- | --- |
| **Presenter** | the best speaker | Talks. Explains each step while the screen shows it. |
| **Driver** | owner of the laptop with Ollama | Runs `chaos-doctor live`, scrolls the page and presses **Live battle** when the presenter is ready. |
| **Backup** | the third person | Keeps the GitHub repo and the [public demo site](https://yashasm18.github.io/chaos-doctor/) open on a second laptop, has the `--offline` fallback ready, answers code questions. |

## Before judging (do this by 5:15 PM)

On the **Driver's** laptop:

```bash
git pull                                   # latest main
pip install -e ".[dev]"                    # inside the .venv
ollama serve                               # leave running (Windows: the Ollama app in the tray)
ollama pull qwen3:8b                       # 16 GB RAM / GPU; use qwen3:4b on 8 GB laptops
ollama run qwen3:8b "say ready"            # warm-up: loads the model into memory once
```

Then a dry run of the **live page**:

```bash
chaos-doctor live --model qwen3:8b
```

It opens the demo page in the browser, served from this laptop. In **The battle**, a new tab
appears: **● Live battle · qwen3:8b · this laptop**. Press it and let one battle run to the end
("Battle over: 0 → 100/100"). Note how long it took. If port 8765 is busy it picks the next free
one and prints the address.

Checklist:

- [ ] Dry run finished with "Battle over" (note the time)
- [ ] Browser is full screen (F11 / Ctrl+Cmd+F) and zoomed so the back row can read it
- [ ] Other heavy apps are closed (the model needs the RAM)
- [ ] Laptop is charged and plugged in; Wi-Fi is not needed, everything is local
- [ ] Backup laptop has the repo open and `python scripts/live_demo.py --offline` ready
- [ ] Everyone is wearing their wristband

Windows (PowerShell): activate with `.venv\Scripts\Activate.ps1`; the command is the same.

## The demo, from the start

Run `chaos-doctor live --model qwen3:8b` before the judges arrive and keep the page at the top.

| Part | On screen | Say (in your own words) |
| --- | --- | --- |
| 1 · What it is (30 s) | Top of the page: headline, the 4 numbers, the 3 problem cards | "Agents break in production: models time out, tools crash, replies come back garbled, data hides instructions. Chaos Doctor breaks your agent on purpose, finds why with a local open-weight model, fixes the code and proves it with a score." |
| 2 · How it works (45 s) | **How it works**: press **Walk me through it** | "Two open-weight models take turns. agentic-chaos from DeepAgentLabs does the breaking and the judging. The Doctor fixes, the Attacker finds the next weakness. Everything grey is plain code: the AI only chooses, it never free-writes code." |
| 3 · The live fight (3-5 min) | **The battle → ● Live battle** | Narrate as it streams, below. |
| 4 · Proof (1 min) | **Results**, then GitHub | "On 20 planted bugs the 4B model fixed 18 by itself. Green CI, an Agent Skill, AIOS export, every change via a reviewed PR." |

**Narrating the live fight.** The caption always says what is happening; read it and add:

| When you see | Say |
| --- | --- |
| Round 1, all tiles ✗, score **0/100** | "Five real failures injected. Every one crashes or fools the agent." |
| "**Doctor AI** (qwen3:8b) is thinking… 12 s", Doctor panel glowing | "That's a real call to the model on this laptop, right now. It's reading the failure and the code." |
| Doctor card: root cause, `@guards.retry(...)`, confidence | "It answered in JSON: the cause, the fix from a fixed menu, and where to put it." |
| A highlighted line appears in the code, score goes up, "✓ Kept" | "One decorator added with Python's ast. We re-test everything; it's kept only because the score went up." |
| "**Attacker AI** is thinking about its next attack…", then a red card "chosen by AI" | "Now the other AI reads the patched code and looks for what's still unprotected." Read its reason out loud. |
| Score drops, then the Doctor answers (often `@guards.sanitize`) | "It found a hole: a prompt injection hidden in the order data. Watch the Doctor close it." |
| "Battle over: 0 → 100/100" | "From zero to battle-tested, live. Every highlighted line is a real diff." |

While a model is thinking (20-60 s), point at the code panel, the tiles, or the Attacker's
reasoning. You can also click earlier timeline steps to recap; the page catches up to the live
step when you click the last one.

**Terminal alternative:** `python scripts/live_demo.py --model qwen3:8b` runs the same battle in
the terminal, pausing for Enter at each step.

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
| No "Live battle" tab | The page must be opened from `chaos-doctor live`, not GitHub Pages. Check the address it printed. |
| Ollama not running / model missing | The script says so and continues with the rule-based Doctor. Or start `ollama serve` and rerun. |
| The model is very slow | Stop with Ctrl+C and start `chaos-doctor live --offline` (the same live page, rule-based Doctor, seconds). Or show the "Real AI battle" recording. |
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

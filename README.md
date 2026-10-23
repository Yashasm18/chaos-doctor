# Chaos Doctor

[![CI](https://github.com/Yashasm18/chaos-doctor/actions/workflows/ci.yml/badge.svg)](https://github.com/Yashasm18/chaos-doctor/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Agent Skill](https://img.shields.io/badge/Agent%20Skill-validated-purple.svg)](chaos-doctor/SKILL.md)

**Two open-weight AIs fight over your agent. One attacks it, one heals it, until it's battle-tested.**

AI agents break in production: the model times out, a tool crashes, the reply comes back
garbled, or someone hides an instruction in the data. Chaos Doctor breaks your agent on purpose,
explains why it broke with a local open-weight model, patches the code, and proves the fix
with a resilience score.

Built at Hacktoberfest Hack Day Bengaluru 2026 for the **Best Open-Source AI Project** track.

```
Round 1  Attacked:   0/100   5 standard faults, every one crashes the agent
         Doctor:     retry on ask_llm()        0 -> 60   kept
         Doctor:     retry on get_order()     60 -> 80   kept
         Doctor:     validate_output on ask_llm()  80 -> 100  kept
Round 2  Attacker:   prompt_injection hidden in lookup_order's data
         Attacked:  83/100
         Doctor:     sanitize on get_order()  83 -> 100  kept
```

## How it works

```
 Attacker AI ──> Scan + score ──> Doctor AI ──> Verify ──┐
 invents an      runs faults      finds root     re-tests,│
 attack          5 per attack     cause, patch   rollback │
      ^                                          if worse │
      └──────────── next round, until score >= 90 ────────┘
```

1. **Scan.** Faults from [agentic-chaos](https://github.com/DeepAgentLabs/agentic-chaos) are
   injected into the agent's model client and tools. Each run is judged by agentic-chaos
   contracts (`NoUnhandledError`, `MaxRetries`) plus the agent's own answer check.
2. **Score.** Average pass rate across attacks, 0 to 100.
3. **Diagnose.** The Doctor model reads the failure and the source and answers in JSON: root
   cause, which function, which recipe, which parameters.
4. **Patch.** The patcher adds one guard decorator (`@guards.retry`, `@guards.sanitize`, ...)
   with Python's `ast`, so the result always parses. See
   [the recipe menu](chaos-doctor/references/RECIPES.md).
5. **Verify.** Re-scan. A patch that lowers the score is rolled back.
6. **Attack again.** The Attacker model reads the patched code and picks the next attack from
   [the attack menu](chaos-doctor/references/FAULTS.md), including prompt injections it writes
   itself.

Small models are reliable here because both AIs choose from fixed menus and fill in details;
the templates do the code changes.

## Quickstart

```bash
git clone https://github.com/Yashasm18/chaos-doctor.git && cd chaos-doctor
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# No model needed: rule-based doctor and attacker
chaos-doctor battle examples/shop_agent/agent.py --offline
```

With the open-weight model:

```bash
ollama pull qwen3:8b          # or qwen3:4b on an 8 GB laptop
export CHAOS_DOCTOR_MODEL=qwen3:8b
chaos-doctor battle examples/shop_agent/agent.py
```

Step by step:

```bash
chaos-doctor scan examples/shop_agent/agent.py               # score + failures
chaos-doctor diagnose examples/shop_agent/agent.py           # root cause
chaos-doctor fix examples/shop_agent/agent.py                # show the diff (dry run)
chaos-doctor fix examples/shop_agent/agent.py --apply        # write it
chaos-doctor verify examples/shop_agent/agent.py             # before -> after
chaos-doctor scan examples/shop_agent/agent.py --min-score 70  # CI gate
```

`battle` works on a copy in `.chaos-doctor/battle-<time>/` and writes a `battle.json` log.

### Settings

| Variable | Default | Meaning |
| --- | --- | --- |
| `CHAOS_DOCTOR_MODEL` | `qwen3:8b` | Model for the Doctor and the Attacker |
| `CHAOS_DOCTOR_OLLAMA_URL` | `http://localhost:11434` | Ollama server, can be a teammate's machine |
| `CHAOS_DOCTOR_TRIALS` | `3` | Runs per attack |
| `CHAOS_DOCTOR_ROUNDS` | `5` | Max battle rounds |
| `CHAOS_DOCTOR_TARGET` | `90` | Score that ends the battle (after round 3) |
| `CHAOS_DOCTOR_VICTIM_MODEL` | unset | Run the demo agent on a real model (e.g. `qwen3:0.6b`) instead of its simulator |

## Use it as an Agent Skill

[`chaos-doctor/`](chaos-doctor/SKILL.md) follows the
[Agent Skills specification](https://agentskills.io/specification) and passes
`agentskills validate`. Copy the folder into your harness's skills directory (for example
`.opencode/skills/` for [OpenCode](https://opencode.ai/docs/skills) or `.claude/skills/`), then
ask your agent to "battle-test my agent".

## Test your own agent

Expose `client`, `TOOLS`, `TASKS`, `run(task)` and `check(task, answer)` in one file. See
[the agent contract](chaos-doctor/references/AGENT_CONTRACT.md) and
[the demo shop agent](examples/shop_agent/agent.py).

## Model and dependencies

| Component | What we use | License / terms |
| --- | --- | --- |
| Doctor + Attacker model | [Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B) (8B parameters, a small language model), or [Qwen3-4B](https://huggingface.co/Qwen/Qwen3-4B) on 8 GB laptops, served by [Ollama](https://ollama.com) | [Apache-2.0](https://huggingface.co/Qwen/Qwen3-8B/blob/main/LICENSE) (open-weight) |
| Fault injection + contracts | [agentic-chaos](https://github.com/DeepAgentLabs/agentic-chaos) 0.8 | Apache-2.0 |
| Synthetic shop data | [great-generator](https://github.com/GreatDataLabs/great-generator) | MIT |
| Model client | [openai](https://github.com/openai/openai-python) (Ollama's OpenAI-compatible API), [httpx](https://github.com/encode/httpx) | Apache-2.0, BSD-3 |
| CLI | [Typer](https://github.com/fastapi/typer), [Rich](https://github.com/Textualize/rich) | MIT |

No real customer data is used: the demo database is generated by
`examples/shop_agent/make_data.py`.

## Project layout

```
chaos-doctor/            the Agent Skill (SKILL.md, references/, scripts/)
src/chaos_doctor/
  attacks.py             attack menu built on agentic-chaos faults
  scan.py                runs attacks, applies contracts, computes the score
  doctor.py              Doctor AI (diagnosis) + rule-based fallback
  attacker.py            Attacker AI (next attack) + fallback
  recipes.py, guards.py  fix recipes and the decorators they insert
  patcher.py             ast-based patching and diffs
  battle.py              the Attacker vs Doctor loop
  cli.py                 chaos-doctor command
examples/shop_agent/     the fragile demo agent and its synthetic data
tests/                   pytest suite (runs offline)
```

## Team

Built by a team of three at Hacktoberfest Hack Day Bengaluru 2026. See
[CONTRIBUTING.md](CONTRIBUTING.md) to get involved.

AI coding assistants helped write parts of this project; every change was reviewed and is
understood by the team.

## License

[Apache-2.0](LICENSE)

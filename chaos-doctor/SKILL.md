---
name: chaos-doctor
description: Tests how well an LLM agent survives failures, then finds and fixes the weak spots. Injects faults (model timeouts, rate-limit storms, tool errors, garbled output, too-long prompts, prompt injection hidden in tool data), gives a resilience score from 0 to 100, uses a local open-weight model to explain the root cause, patches the code with a small reviewed decorator, and re-tests to prove the fix. Use when the user asks to test, harden, battle-test or check the reliability or resilience of an AI agent, or mentions chaos testing, fault injection, retries, timeouts, fallbacks or prompt injection in an agent.
license: Apache-2.0
compatibility: Requires Python 3.10+, the chaos-doctor package (pip install -e . from the repo), and Ollama running locally with qwen3:8b or qwen3:4b pulled. Use --offline to run without a model.
metadata:
  author: chaos-doctor-team
  version: "0.1.0"
  repository: https://github.com/Yashasm18/chaos-doctor
---

# Chaos Doctor

Break an agent on purpose, find why it broke, fix it, and prove it is stronger.

## Before you start

1. Find the agent's entry file. It must expose `client`, `TOOLS`, `TASKS`, `run(task)` and
   `check(task, answer)`. See [references/AGENT_CONTRACT.md](references/AGENT_CONTRACT.md).
   If the user's agent does not have these, offer to add a thin adapter file.
2. Check the model is reachable: `scripts/doctor_check.sh`. If it fails, tell the user to run
   `ollama serve` and `ollama pull qwen3:4b`, or continue with `--offline`.

## Steps

1. **Scan** the agent and report the score and which attacks failed:
   `chaos-doctor scan <agent.py>`
2. If the score is below 90, **diagnose** the worst failure:
   `chaos-doctor diagnose <agent.py>`
   Explain the root cause to the user in one or two sentences.
3. **Propose the fix** and show the diff:
   `chaos-doctor fix <agent.py>`
   Only apply it after the user agrees: `chaos-doctor fix <agent.py> --apply`
4. **Verify** and report the before and after score:
   `chaos-doctor verify <agent.py>`
5. For a full hardening run, use the **battle** loop. It works on a copy and never touches the
   original file:
   `chaos-doctor battle <agent.py>`
   Report the score history and point the user to the patched copy and its `battle.json` log.

## What the attacks and fixes mean

- Attacks: [references/FAULTS.md](references/FAULTS.md)
- Fix recipes: [references/RECIPES.md](references/RECIPES.md)

## Edge cases

- Score already 90 or more: report it and stop. Nothing to fix.
- A patch lowers the score: the battle loop rolls it back automatically; say so.
- Model reply is invalid: the Doctor falls back to its rule-based diagnosis and labels it
  `(rules)`. Mention this to the user.
- CI usage: `chaos-doctor scan <agent.py> --min-score 70` exits 1 below the gate.

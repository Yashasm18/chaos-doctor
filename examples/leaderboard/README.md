# Agent pattern leaderboard

How common agent designs hold up under Chaos Doctor, before and after an offline battle.

These agents are **patterns we wrote from scratch**, following the shapes most tutorials and
framework docs use. They are not copies of third-party projects: the public example repos we
looked at (including DeepAgentLabs `Usecases`) carry no license, so we did not adapt their
code. Each agent uses the simulated model in `chaos_doctor.simulated`, so results are
repeatable offline.

| Agent pattern | What it does | Before | After battle | What the Doctor added |
| --- | --- | --- | --- | --- |
| [Shop support](../shop_agent/agent.py) (demo) | Order lookup tool + one model call | **0** | **100** | retry, validate_output on the model call; retry, sanitize on the tool caller |
| [RAG answerer](rag_answerer/agent.py) | Search a knowledge base, answer from the hit | **0** | **100** | retry (raised to 6 attempts), validate_output on `answer`; retry, sanitize on `retrieve` |
| [Two-step router](two_step_router/agent.py) | Model picks a route, tool runs, model replies | **20** | **100** | retry (6 attempts) on `classify`; retry, sanitize on `fetch_account` |
| [Hand-hardened](hand_hardened/agent.py) | Already has try/except + retry loops | **80** | **83** | validate_output on `call_model`; sanitize on `get_parcel` |

Logs: [`results/`](results/). Reproduce one row:

```bash
chaos-doctor battle examples/leaderboard/rag_answerer/agent.py --offline --trials 2 --rounds 4
```

## What we learned

- **Unprotected agents score 0.** Any single timeout, 429, tool error or too-long prompt
  escapes as an exception.
- **Hand-written try/except catches crashes but not garbage.** The hand-hardened agent survives
  every crash-type fault (80/100) but passes garbled model output straight to the user. The
  Doctor fixed that with `validate_output`.
- **Swallowed errors hide failures, from users and from tools.** The hand-hardened agent's own
  loop turns a long 429 storm into "Sorry, please try again later." No exception escapes, so
  adding `retry` cannot help, and the battle correctly rolled that patch back (it stays at
  83). The real fix is to let the error escape or retry for longer inside the loop, which needs
  a human decision about the fallback text.
- **Known gap in our scanner: only the first model call is attacked.** Flaky faults fire on the
  first call they see and then recover. In the two-step router that is `classify`, so the
  second call (`respond`) is never exercised and stays unguarded even at 100/100. Attacking
  each call site separately is a good next issue.

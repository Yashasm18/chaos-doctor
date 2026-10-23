# Contributing to Chaos Doctor

Thanks for helping make agents tougher. First-time contributors are welcome.

## Set up

```bash
git clone https://github.com/Yashasm18/chaos-doctor.git && cd chaos-doctor
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,data]"
pytest
```

The test suite runs offline. To try the real Doctor, install [Ollama](https://ollama.com) and
`ollama pull qwen3:4b`.

## Workflow

1. Pick or open an issue and assign yourself.
2. Branch from `main`: `feat/<short-name>`, `fix/<short-name>` or `docs/<short-name>`.
3. Keep commits small. Message style: `feat(doctor): add timeout recipe`.
4. Run `ruff check . && ruff format --check . && pytest` before pushing.
5. Open a pull request using the template and link the issue (`Closes #12`).
6. Another contributor reviews and approves before merge. `main` is protected.

## Good first contributions

- A new fix recipe: add a decorator to `guards.py`, register it in `recipes.py`, document it
  in `chaos-doctor/references/RECIPES.md`, and add a test.
- A new attack: add it to `attacks.py` and `attacker.py`'s menu, document it in
  `chaos-doctor/references/FAULTS.md`.
- An adapter that makes a LangGraph or CrewAI agent follow the
  [agent contract](chaos-doctor/references/AGENT_CONTRACT.md).

## Code of conduct

We follow the [MLH Code of Conduct](https://static.mlh.io/docs/mlh-code-of-conduct.pdf).
Be kind and constructive in reviews.

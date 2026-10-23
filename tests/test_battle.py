"""End-to-end checks on the demo agent with the simulated model and rule-based doctor."""

from pathlib import Path

from chaos_doctor import attacker, doctor
from chaos_doctor.attacks import Attack, standard_attacks
from chaos_doctor.battle import battle
from chaos_doctor.scan import scan

AGENT = Path(__file__).parents[1] / "examples" / "shop_agent" / "agent.py"


def test_fragile_agent_fails_every_standard_attack():
    result = scan(AGENT, standard_attacks(["lookup_order"]), trials=1)
    assert result.score == 0
    assert len(result.failing) == 5


def test_prompt_injection_is_detected():
    result = scan(AGENT, [Attack("prompt_injection", "lookup_order")], trials=1)
    assert "prompt injection succeeded" in result.results[0].failures[0]


def test_offline_battle_heals_the_agent(tmp_path):
    log = battle(AGENT, tmp_path / "run", llm=None, model_name="rules", trials=1, max_rounds=3)
    scores = [s["score"] for s in log.scores]
    assert scores[0] == 0
    assert scores[-1] == 100
    patched = (tmp_path / "run" / "agent.py").read_text()
    assert "@guards.retry" in patched and "@guards.sanitize" in patched
    assert (tmp_path / "run" / "battle.json").exists()


def test_doctor_falls_back_to_rules_when_model_is_invalid():
    result = scan(AGENT, [Attack("rate_limit_storm")], trials=1).results[0]

    def bad_llm(system, user, schema):
        return {"target_function": "not_a_function", "recipe": "magic", "confidence": 1}

    diag = doctor.diagnose(bad_llm, AGENT.read_text(), result)
    assert diag.source == "rules"
    assert diag.target_function == "ask_llm"


def test_doctor_uses_valid_model_answer():
    result = scan(AGENT, [Attack("rate_limit_storm")], trials=1).results[0]

    def good_llm(system, user, schema):
        assert "ask_llm" in schema["properties"]["target_function"]["enum"]
        return {
            "root_cause": "no retry around the model call",
            "target_function": "ask_llm",
            "recipe": "retry",
            "params": {"attempts": 5},
            "confidence": 0.9,
            "explanation": "429s escape ask_llm",
        }

    diag = doctor.diagnose(good_llm, AGENT.read_text(), result)
    assert (diag.source, diag.recipe, diag.params["attempts"]) == ("llm", "retry", 5)


def test_attacker_output_is_normalised():
    def llm(system, user, schema):
        return {"kind": "prompt_injection", "target": "llm", "params": {}, "rationale": "x"}

    attack = attacker.propose(llm, AGENT.read_text(), [], ["lookup_order"])
    assert attack.target == "lookup_order"
    assert "PWNED-42" in attack.params["payload"]


def test_noop_model_fix_is_strengthened_by_rules(tmp_path):
    """If the model re-picks an existing guard unchanged, heal() strengthens it instead."""
    from chaos_doctor.battle import heal
    from chaos_doctor.patcher import apply_recipe

    work = tmp_path / "agent"
    import shutil

    shutil.copytree(AGENT.parent, work, ignore=shutil.ignore_patterns("__pycache__"))
    agent = work / "agent.py"
    agent.write_text(apply_recipe(agent.read_text(), "ask_llm", "retry", {"attempts": 4}))
    attacks = [Attack("rate_limit_storm", "llm", {"burst_count": 4})]
    before = scan(agent, attacks, trials=1)
    assert before.score == 0

    def lazy_llm(system, user, schema):
        return {
            "root_cause": "429s",
            "target_function": "ask_llm",
            "recipe": "retry",
            "params": {"attempts": 4, "backoff_s": 0.05},
            "confidence": 0.8,
            "explanation": "retry",
        }

    after = heal(agent, attacks, before, lazy_llm, trials=1, emit=lambda *a: None)
    assert after.score == 100
    assert "attempts=6" in agent.read_text()

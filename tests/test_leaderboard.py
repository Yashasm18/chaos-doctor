"""The leaderboard agents follow the agent contract and keep their recorded starting scores."""

from pathlib import Path

import pytest

from chaos_doctor.attacks import standard_attacks
from chaos_doctor.scan import load_agent, scan

LB = Path(__file__).parents[1] / "examples" / "leaderboard"


@pytest.mark.parametrize(
    "name, before", [("rag_answerer", 0), ("two_step_router", 20), ("hand_hardened", 80)]
)
def test_leaderboard_agent_starting_score(name, before):
    agent = LB / name / "agent.py"
    tools = list(load_agent(agent).TOOLS)
    assert scan(agent, standard_attacks(tools), trials=1).score == before

"""Every benchmark case plants a real weakness, and the rule-based Doctor can fix it."""

import importlib.util
import sys
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "benchmark_run", Path(__file__).parents[1] / "benchmark" / "run.py"
)
bench = importlib.util.module_from_spec(spec)
sys.modules["benchmark_run"] = bench  # dataclasses look their module up here
spec.loader.exec_module(bench)

CASES = bench.cases()


def test_there_are_twenty_cases():
    assert len(CASES) == 20
    assert len({c.id for c in CASES}) == 20


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_case_is_valid_and_fixable(case):
    out = bench.run_case(case, llm=None)  # run_case asserts the weakness breaks the agent
    assert out.fixed
    assert out.function == out.expected_function

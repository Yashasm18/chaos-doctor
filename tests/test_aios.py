import json
import urllib.request
from pathlib import Path

import pytest

from chaos_doctor.aios_export import EXTENSION, scan_to_runs, write_runs
from chaos_doctor.attacks import Attack
from chaos_doctor.scan import scan

AGENT = Path(__file__).parents[1] / "examples" / "shop_agent" / "agent.py"
SCHEMA_BASE = (
    "https://raw.githubusercontent.com/DeepAgentLabs/ai-operations-spec/main/"
    "specification/v0.4/schemas/"
)


@pytest.fixture(scope="module")
def runs():
    result = scan(AGENT, [Attack("rate_limit_storm"), Attack("tool_failure", "lookup_order")], 2)
    return scan_to_runs(result, {"battle_round": 1})


def test_one_run_per_trial_with_our_extension(runs):
    assert len(runs) == 4
    for run in runs:
        assert run["spec_version"] == "0.4-draft"
        assert run["artifact_type"] == "run"
        ext = run["extensions"][EXTENSION]
        assert ext["verdict"] == "failed"  # the fragile agent fails both attacks
        assert ext["battle_round"] == 1
        assert run["status"] == "failed"  # the fault escaped the agent


def test_write_runs(tmp_path, runs):
    paths = write_runs(runs, tmp_path, prefix="r1-")
    assert len(paths) == 4
    assert paths[0].name.startswith("r1-000-rate_limit_storm")
    assert json.loads(paths[0].read_text())["id"] == runs[0]["id"]


def _schema(name):
    try:
        with urllib.request.urlopen(SCHEMA_BASE + name, timeout=10) as resp:
            return json.load(resp)
    except OSError as exc:
        pytest.skip(f"AIOS schema not reachable: {exc}")


def test_runs_validate_against_aios_v04_schema(runs):
    jsonschema = pytest.importorskip("jsonschema")
    referencing = pytest.importorskip("referencing")
    run_schema, common = _schema("run.schema.json"), _schema("common.schema.json")
    registry = referencing.Registry().with_resources(
        [
            (run_schema["$id"], referencing.Resource.from_contents(run_schema)),
            (
                run_schema["$id"].replace("run.schema", "common.schema"),
                referencing.Resource.from_contents(common),
            ),
        ]
    )
    validator = jsonschema.Draft202012Validator(run_schema, registry=registry)
    for run in runs:
        errors = list(validator.iter_errors(run))
        assert not errors, errors[0].message

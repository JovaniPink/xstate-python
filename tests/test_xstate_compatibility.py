"""The comparison gate must reject shared wrong results and hidden gap drift.

These tests need no Node installation; the separate compatibility CI job runs
the real JS/Python comparison. This suite checks the gate's failure behavior.
"""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "compare_xstate_v5", ROOT / "scripts" / "compare_xstate_v5.py"
)
assert SPEC is not None and SPEC.loader is not None
comparison = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(comparison)
FIXTURES = {
    fixture["id"]: fixture
    for fixture in json.loads((comparison.REFERENCE / "fixtures.json").read_text())
}


def test_empty_corpus_cannot_pass():
    with pytest.raises(ValueError, match="non-empty list"):
        comparison.validate_fixtures([])


def test_duplicate_ids_cannot_overwrite_reference_results():
    fixture = FIXTURES["numeric-delay"]
    with pytest.raises(ValueError, match="duplicate fixture id: numeric-delay"):
        comparison.validate_fixtures([fixture, deepcopy(fixture)])


@pytest.mark.parametrize("key", ["expected", "expected_python"])
def test_every_command_requires_an_expected_observation(key):
    fixture = deepcopy(FIXTURES["tied-delay-key-order"])
    fixture[key].pop()
    with pytest.raises(ValueError, match=f"{key} must contain one observation"):
        comparison.validate_fixtures([fixture])


def test_same_wrong_result_from_both_runtimes_is_rejected():
    fixture = FIXTURES["numeric-delay"]
    wrong = deepcopy(fixture["expected"])
    wrong[2]["value"] = "waiting"
    failures = comparison.check_fixture(fixture, wrong, wrong)
    assert len(failures) == 2
    assert all("command[2]" in failure for failure in failures)
    assert all("snapshot.value expected='done' actual='waiting'" in f for f in failures)


def test_causal_action_argument_drift_names_the_field():
    fixture = FIXTURES["causal-action-arguments"]
    changed = deepcopy(fixture["expected"])
    changed[2]["actions"][2]["event"]["type"] = "GO"
    failures = comparison.check_fixture(fixture, changed, fixture["expected"])
    assert len(failures) == 1
    assert "causal-action-arguments command[2] Python" in failures[0]
    assert "snapshot.actions[2].event.type expected='INNER' actual='GO'" in failures[0]


def test_fixed_known_gap_requires_explicit_promotion():
    fixture = FIXTURES["tied-delay-key-order"]
    failures = comparison.check_fixture(
        fixture, fixture["expected"], fixture["expected"]
    )
    assert any("unexpected parity" in failure for failure in failures)


def test_action_order_is_not_normalized_away():
    fixture = FIXTURES["causal-action-arguments"]
    changed = deepcopy(fixture["expected"])
    changed[2]["actions"].reverse()
    failures = comparison.check_fixture(fixture, fixture["expected"], changed)
    assert len(failures) == 1
    assert "command[2] XState: snapshot.actions[0]" in failures[0]


def test_distinct_python_oracle_requires_known_difference():
    fixture = deepcopy(FIXTURES["numeric-delay"])
    fixture["expected_python"] = deepcopy(fixture["expected"])
    fixture["expected_python"][2]["value"] = "waiting"
    failures = comparison.check_fixture(
        fixture, fixture["expected_python"], fixture["expected"]
    )
    assert failures == ["numeric-delay: known-difference metadata and oracles disagree"]

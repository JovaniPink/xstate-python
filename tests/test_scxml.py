import json
from pathlib import Path
from pprint import PrettyPrinter

import pytest

from xstate.scxml import scxml_to_machine

pp = PrettyPrinter(indent=2)

test_dir = Path(__file__).resolve().parent / "fixtures" / "scxml"

test_groups: dict[str, list[str]] = {
    "actionSend": [
        "send1",
        "send2",
        "send3",
        "send4",
        "send4b",
        "send7",
        "send7b",
        "send8",
        "send8b",
        "send9",
    ],
    # "assign": ["assign_invalid", "assign_obj_literal"],
    "basic": ["basic0", "basic1", "basic2"],
    "cond-js": ["test0", "test1", "test2", "TestConditionalTransition"],
    "default-initial-state": ["initial1", "initial2"],
    "documentOrder": ["documentOrder0"],
    "hierarchy": ["hier0", "hier1", "hier2"],
    "hierarchy+documentOrder": ["test0", "test1"],
    "parallel": ["test0", "test1", "test2", "test3"],
    "parallel+interrupt": [
        "test0",
        "test1",
        "test2",
        "test3",
        "test4",
        "test5",
        "test6",
        "test7",
        "test8",
        "test9",
        "test10",
    ],
    "more-parallel": [
        "test0",
        "test1",
        "test2",
        "test2b",
        "test3",
        "test3b",
        "test4",
        "test5",
        "test6",
        "test6b",
        "test7",
        "test8",
        "test9",
        "test10",
        "test10b",
    ],
}

scxml_ci_groups = {
    "actionSend",
    "basic",
    "cond-js",
    "default-initial-state",
    "documentOrder",
    "hierarchy",
    "hierarchy+documentOrder",
    "parallel",
    "parallel+interrupt",
    "more-parallel",
}

test_files = [
    pytest.param(
        test_dir / test_group / f"{test_name}.scxml",
        test_dir / test_group / f"{test_name}.json",
        id=f"{test_group}/{test_name}",
        marks=pytest.mark.scxml_ci if test_group in scxml_ci_groups else (),
    )
    for test_group, test_names in test_groups.items()
    for test_name in test_names
]


@pytest.mark.scxml_ci
def test_vendored_scxml_fixture_inventory_is_exact() -> None:
    expected = {
        test_dir / test_group / f"{test_name}{suffix}"
        for test_group, test_names in test_groups.items()
        for test_name in test_names
        for suffix in (".json", ".scxml")
    }
    actual = set(test_dir.glob("*/*.json")) | set(test_dir.glob("*/*.scxml"))

    assert actual == expected
    provenance = (test_dir / "PROVENANCE.md").read_text(encoding="utf-8")
    assert "b46a10a1c3a3b1ca5c5cb4bb44ddb5c785611f41" in provenance
    assert (test_dir / "LICENSE.txt").is_file()


@pytest.mark.scxml_ci
def test_scxml_to_machine_accepts_path_source():
    machine = scxml_to_machine(test_dir / "basic" / "basic0.scxml")

    assert machine.initial_state.matches("a")


@pytest.mark.parametrize("scxml_source,scxml_test_source", test_files)
def test_scxml(scxml_source, scxml_test_source):
    machine = scxml_to_machine(scxml_source)

    try:
        state = machine.initial_state

        with scxml_test_source.open(encoding="utf-8") as scxml_test_file:
            scxml_test = json.load(scxml_test_file)

            for event_test in scxml_test.get("events"):
                event_to_send = event_test.get("event")
                event_name = event_to_send.get("name")
                next_configuration = event_test.get("nextConfiguration")

                state = machine.transition(state, event_name)

                assert sorted(
                    [sn.key for sn in state.configuration if sn.type == "atomic"]
                ) == sorted(next_configuration)
    except Exception:
        pp.pprint(machine.config)
        raise

import xml.etree.ElementTree as ET
from typing import Optional, Dict, List
import json
import pytest
from xstate.scxml import scxml_to_machine
from pprint import PrettyPrinter

pp = PrettyPrinter(indent=2)

test_dir = "test-framework/test"

test_groups: Dict[str, List[str]] = {
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
}

test_files = [
    (
        f"{test_dir}/{test_group}/{test_name}.scxml",
        f"{test_dir}/{test_group}/{test_name}.json",
    )
    for test_group, test_names in test_groups.items()
    for test_name in test_names
]


@pytest.mark.parametrize("scxml_source,scxml_test_source", test_files)
def test_scxml(scxml_source, scxml_test_source):
    machine = scxml_to_machine(scxml_source)

    try:
        state = machine.initial_state

        with open(scxml_test_source) as scxml_test_file:
            scxml_test = json.load(scxml_test_file)

            for event_test in scxml_test.get("events"):
                event_to_send = event_test.get("event")
                event_name = event_to_send.get("name")
                next_configuration = event_test.get("nextConfiguration")

                state = machine.transition(state, event_name)

                assert sorted(
                    [sn.key for sn in state.configuration if sn.type == "atomic"]
                ) == sorted(next_configuration)
    except:
        pp.pprint(machine.config)
        raise

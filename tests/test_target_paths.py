"""XState v5 transition target path compatibility."""

import pytest

from xstate import Machine
from xstate.exceptions import InvalidConfigError


def test_sibling_target():
    machine = Machine(
        {
            "id": "siblings",
            "initial": "a",
            "states": {"a": {"on": {"GO": "b"}}, "b": {}},
        }
    )

    assert machine.transition(machine.initial_state, "GO").value == "b"


def test_sibling_descendant_target():
    machine = Machine(
        {
            "id": "sibling-descendant",
            "initial": "a",
            "states": {
                "a": {"on": {"GO": "b.c"}},
                "b": {
                    "initial": "d",
                    "states": {"c": {}, "d": {}},
                },
            },
        }
    )

    assert machine.transition(machine.initial_state, "GO").value == {"b": "c"}


def test_dot_prefixed_child_target():
    machine = Machine(
        {
            "id": "child-target",
            "initial": "a",
            "states": {
                "a": {
                    "initial": "first",
                    "states": {"first": {}, "child": {}},
                    "on": {"GO": ".child"},
                }
            },
        }
    )

    assert machine.transition(machine.initial_state, "GO").value == {"a": "child"}


def test_root_dot_prefixed_child_target():
    machine = Machine(
        {
            "id": "root-child",
            "initial": "a",
            "on": {"GO": ".b"},
            "states": {"a": {}, "b": {}},
        }
    )

    assert machine.transition(machine.initial_state, "GO").value == "b"


def test_id_target_remains_supported():
    machine = Machine(
        {
            "id": "ids",
            "initial": "a",
            "states": {
                "a": {"on": {"GO": "#destination"}},
                "b": {"id": "destination"},
            },
        }
    )

    assert machine.transition(machine.initial_state, "GO").value == "b"


def test_multiple_sibling_descendant_targets():
    machine = Machine(
        {
            "id": "multiple",
            "initial": "idle",
            "states": {
                "idle": {
                    "on": {"GO": {"target": ["active.left.on", "active.right.on"]}}
                },
                "active": {
                    "type": "parallel",
                    "states": {
                        "left": {
                            "initial": "off",
                            "states": {"off": {}, "on": {}},
                        },
                        "right": {
                            "initial": "off",
                            "states": {"off": {}, "on": {}},
                        },
                    },
                },
            },
        }
    )

    assert machine.transition(machine.initial_state, "GO").value == {
        "active": {"left": "on", "right": "on"}
    }


def test_invalid_descendant_target_path_is_rejected():
    with pytest.raises(InvalidConfigError, match="b.missing"):
        Machine(
            {
                "id": "invalid-path",
                "initial": "a",
                "states": {
                    "a": {"on": {"GO": "b.missing"}},
                    "b": {"initial": "c", "states": {"c": {}}},
                },
            }
        )

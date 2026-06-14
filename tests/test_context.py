"""Tests for context, assign actions, and pure-Python guards (0.2.0)."""

import pytest

from xstate import Machine, assign


def make_counter(guards=None):
    return Machine(
        {
            "id": "counter",
            "initial": "active",
            "context": {"count": 0},
            "states": {
                "active": {
                    "on": {
                        "INC": {
                            "target": "active",
                            "actions": [
                                assign({"count": lambda ctx, ev: ctx["count"] + 1})
                            ],
                        },
                        "ADD": {
                            "target": "active",
                            "actions": [
                                assign(
                                    lambda ctx, ev: {
                                        "count": ctx["count"] + ev.data["by"]
                                    }
                                )
                            ],
                        },
                        "RESET": {
                            "target": "active",
                            "actions": [assign({"count": 0})],
                        },
                    }
                }
            },
        },
        guards=guards or {},
    )


def test_initial_context_from_config():
    machine = make_counter()
    state = machine.initial_state
    assert state.context == {"count": 0}


def test_assign_with_value_function():
    machine = make_counter()
    state = machine.initial_state
    state = machine.transition(state, "INC")
    assert state.context["count"] == 1
    state = machine.transition(state, "INC")
    assert state.context["count"] == 2


def test_assign_with_static_value():
    machine = make_counter()
    state = machine.initial_state
    state = machine.transition(state, "INC")
    state = machine.transition(state, "INC")
    state = machine.transition(state, "RESET")
    assert state.context["count"] == 0


def test_assign_function_reads_event_data():
    machine = make_counter()
    state = machine.initial_state
    state = machine.transition(state, {"type": "ADD", "by": 5})
    assert state.context["count"] == 5
    state = machine.transition(state, {"type": "ADD", "by": 3})
    assert state.context["count"] == 8


def test_context_is_immutable_between_states():
    machine = make_counter()
    first = machine.initial_state
    second = machine.transition(first, "INC")
    # The original state's context must not be mutated by a later transition.
    assert first.context["count"] == 0
    assert second.context["count"] == 1


def test_guard_callable_blocks_transition():
    machine = Machine(
        {
            "id": "gate",
            "initial": "closed",
            "context": {"allowed": False},
            "states": {
                "closed": {
                    "on": {
                        "OPEN": {
                            "target": "open",
                            "cond": lambda ctx, ev: ctx["allowed"],
                        }
                    }
                },
                "open": {},
            },
        }
    )
    state = machine.initial_state
    # Guard is False -> transition is not taken, stays closed.
    state = machine.transition(state, "OPEN")
    assert state.value == "closed"


def test_guard_callable_allows_transition():
    machine = Machine(
        {
            "id": "gate",
            "initial": "closed",
            "context": {"allowed": True},
            "states": {
                "closed": {
                    "on": {
                        "OPEN": {
                            "target": "open",
                            "cond": lambda ctx, ev: ctx["allowed"],
                        }
                    }
                },
                "open": {},
            },
        }
    )
    state = machine.initial_state
    state = machine.transition(state, "OPEN")
    assert state.value == "open"


def test_named_guard_from_registry():
    machine = Machine(
        {
            "id": "gate",
            "initial": "closed",
            "context": {"count": 3},
            "states": {
                "closed": {
                    "on": {
                        "OPEN": {"target": "open", "cond": "isReady"},
                    }
                },
                "open": {},
            },
        },
        guards={"isReady": lambda ctx, ev: ctx["count"] >= 3},
    )
    state = machine.initial_state
    state = machine.transition(state, "OPEN")
    assert state.value == "open"


def test_guard_uses_event_data():
    machine = Machine(
        {
            "id": "gate",
            "initial": "closed",
            "states": {
                "closed": {
                    "on": {
                        "OPEN": {
                            "target": "open",
                            "cond": lambda ctx, ev: ev.data.get("key") == "secret",
                        }
                    }
                },
                "open": {},
            },
        }
    )
    state = machine.initial_state
    state = machine.transition(state, {"type": "OPEN", "key": "wrong"})
    assert state.value == "closed"
    state = machine.transition(state, {"type": "OPEN", "key": "secret"})
    assert state.value == "open"


def test_missing_named_guard_raises():
    machine = Machine(
        {
            "id": "gate",
            "initial": "closed",
            "states": {
                "closed": {"on": {"OPEN": {"target": "open", "cond": "nope"}}},
                "open": {},
            },
        }
    )
    state = machine.initial_state
    with pytest.raises(ValueError, match="Guard 'nope'"):
        machine.transition(state, "OPEN")

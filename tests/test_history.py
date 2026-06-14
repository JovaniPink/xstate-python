"""Tests for shallow and deep history states (0.2.0)."""

from xstate import Machine


def make_shallow():
    return Machine(
        {
            "id": "power",
            "initial": "off",
            "states": {
                "off": {"on": {"POWER": "#hist"}},
                "on": {
                    "initial": "low",
                    "on": {"POWER": "off"},
                    "states": {
                        "low": {"on": {"SWITCH": "high"}},
                        "high": {"on": {"SWITCH": "low"}},
                        "hist": {"type": "history", "id": "hist"},
                    },
                },
            },
        }
    )


def make_deep():
    return Machine(
        {
            "id": "deep",
            "initial": "off",
            "states": {
                "off": {"on": {"POWER": "#hist"}},
                "on": {
                    "initial": "a",
                    "on": {"POWER": "off"},
                    "states": {
                        "a": {
                            "initial": "a1",
                            "states": {
                                "a1": {"on": {"NEXT": "a2"}},
                                "a2": {},
                            },
                        },
                        "hist": {"type": "history", "history": "deep", "id": "hist"},
                    },
                },
            },
        }
    )


def test_history_default_falls_back_to_parent_initial():
    machine = make_shallow()
    state = machine.initial_state
    assert state.value == "off"
    # First entry through history with no recorded value -> parent's initial.
    state = machine.transition(state, "POWER")
    assert state.value == {"on": "low"}


def test_shallow_history_restores_last_child():
    machine = make_shallow()
    state = machine.initial_state
    state = machine.transition(state, "POWER")  # on.low
    state = machine.transition(state, "SWITCH")  # on.high
    assert state.value == {"on": "high"}
    state = machine.transition(state, "POWER")  # off (records history: high)
    assert state.value == "off"
    state = machine.transition(state, "POWER")  # restore -> high
    assert state.value == {"on": "high"}


def test_shallow_history_updates_on_each_exit():
    machine = make_shallow()
    state = machine.initial_state
    state = machine.transition(state, "POWER")  # low
    state = machine.transition(state, "POWER")  # off (history: low)
    state = machine.transition(state, "POWER")  # restore -> low
    assert state.value == {"on": "low"}
    state = machine.transition(state, "SWITCH")  # high
    state = machine.transition(state, "POWER")  # off (history: high)
    state = machine.transition(state, "POWER")  # restore -> high
    assert state.value == {"on": "high"}


def test_deep_history_restores_nested_atomic_state():
    machine = make_deep()
    state = machine.initial_state
    state = machine.transition(state, "POWER")  # on.a.a1
    assert state.value == {"on": {"a": "a1"}}
    state = machine.transition(state, "NEXT")  # on.a.a2
    assert state.value == {"on": {"a": "a2"}}
    state = machine.transition(state, "POWER")  # off (deep history: a2)
    assert state.value == "off"
    state = machine.transition(state, "POWER")  # restore deep -> a2
    assert state.value == {"on": {"a": "a2"}}

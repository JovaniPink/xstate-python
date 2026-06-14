"""Tests for parallel (orthogonal) states (0.2.0)."""

from xstate import Machine


def make_word():
    """A parallel-root machine with two independent formatting regions."""
    return Machine(
        {
            "id": "word",
            "type": "parallel",
            "states": {
                "bold": {
                    "initial": "off",
                    "states": {
                        "off": {"on": {"TOGGLE_BOLD": "on", "RESET": "off"}},
                        "on": {"on": {"TOGGLE_BOLD": "off", "RESET": "off"}},
                    },
                },
                "italics": {
                    "initial": "off",
                    "states": {
                        "off": {"on": {"TOGGLE_ITALICS": "on", "RESET": "off"}},
                        "on": {"on": {"TOGGLE_ITALICS": "off", "RESET": "off"}},
                    },
                },
            },
        }
    )


def test_parallel_root_initial_enters_all_regions():
    machine = make_word()
    state = machine.initial_state
    assert state.value == {"bold": "off", "italics": "off"}


def test_parallel_regions_transition_independently():
    machine = make_word()
    state = machine.initial_state
    state = machine.transition(state, "TOGGLE_BOLD")
    assert state.value == {"bold": "on", "italics": "off"}
    state = machine.transition(state, "TOGGLE_ITALICS")
    assert state.value == {"bold": "on", "italics": "on"}
    state = machine.transition(state, "TOGGLE_BOLD")
    assert state.value == {"bold": "off", "italics": "on"}


def test_event_handled_by_multiple_regions():
    machine = make_word()
    state = machine.initial_state
    state = machine.transition(state, "TOGGLE_BOLD")
    state = machine.transition(state, "TOGGLE_ITALICS")
    assert state.value == {"bold": "on", "italics": "on"}
    # RESET is handled by both regions at once.
    state = machine.transition(state, "RESET")
    assert state.value == {"bold": "off", "italics": "off"}


def test_nested_parallel_state():
    machine = Machine(
        {
            "id": "app",
            "initial": "editing",
            "states": {
                "editing": {
                    "type": "parallel",
                    "states": {
                        "mode": {
                            "initial": "insert",
                            "states": {
                                "insert": {"on": {"ESC": "command"}},
                                "command": {"on": {"I": "insert"}},
                            },
                        },
                        "saved": {
                            "initial": "clean",
                            "states": {
                                "clean": {"on": {"EDIT": "dirty"}},
                                "dirty": {"on": {"SAVE": "clean"}},
                            },
                        },
                    },
                }
            },
        }
    )
    state = machine.initial_state
    assert state.value == {"editing": {"mode": "insert", "saved": "clean"}}
    state = machine.transition(state, "ESC")
    assert state.value == {"editing": {"mode": "command", "saved": "clean"}}
    state = machine.transition(state, "EDIT")
    assert state.value == {"editing": {"mode": "command", "saved": "dirty"}}


def test_parallel_on_done_when_all_regions_final():
    machine = Machine(
        {
            "id": "p",
            "initial": "running",
            "states": {
                "running": {
                    "type": "parallel",
                    "onDone": "done",
                    "states": {
                        "a": {
                            "initial": "a1",
                            "states": {
                                "a1": {"on": {"FINISH_A": "a2"}},
                                "a2": {"type": "final"},
                            },
                        },
                        "b": {
                            "initial": "b1",
                            "states": {
                                "b1": {"on": {"FINISH_B": "b2"}},
                                "b2": {"type": "final"},
                            },
                        },
                    },
                },
                "done": {"type": "final"},
            },
        }
    )
    state = machine.initial_state
    assert state.value == {"running": {"a": "a1", "b": "b1"}}
    # One region final is not enough.
    state = machine.transition(state, "FINISH_A")
    assert state.value == {"running": {"a": "a2", "b": "b1"}}
    # Both regions final -> done.state.running -> onDone.
    state = machine.transition(state, "FINISH_B")
    assert state.value == "done"

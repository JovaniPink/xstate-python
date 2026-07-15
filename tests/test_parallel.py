"""Tests for parallel (orthogonal) states (0.2.0)."""

import pytest

from xstate import Machine, interpret


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


def test_external_region_transition_reenters_parallel_siblings():
    calls: list[str] = []
    machine = Machine(
        {
            "id": "workflow",
            "initial": "running",
            "states": {
                "running": {
                    "type": "parallel",
                    "states": {
                        "a": {
                            "initial": "a1",
                            "on": {"RESET_A": "#a1"},
                            "states": {
                                "a1": {"id": "a1"},
                                "a2": {},
                            },
                        },
                        "b": {
                            "entry": "enterB",
                            "exit": "exitB",
                            "initial": "b1",
                            "states": {
                                "b1": {"on": {"ADVANCE_B": "b2"}},
                                "b2": {},
                            },
                        },
                    },
                }
            },
        },
        actions={
            "enterB": lambda: calls.append("enterB"),
            "exitB": lambda: calls.append("exitB"),
        },
    )
    service = interpret(machine).start()
    calls.clear()

    service.send("ADVANCE_B")
    assert service.state.value == {"running": {"a": "a1", "b": "b2"}}

    service.send("RESET_A")

    assert service.state.value == {"running": {"a": "a1", "b": "b1"}}
    assert calls == ["exitB", "enterB"]
    service.stop()


def _parallel_conflict_machine(first_region: str) -> Machine:
    a = {
        "initial": "a1",
        "on": {"T": "#a2"},
        "states": {
            "a1": {},
            "a2": {"id": "a2"},
        },
    }
    b = {
        "initial": "b1",
        "states": {
            "b1": {"on": {"T": "b2"}},
            "b2": {},
        },
    }
    regions = {"a": a, "b": b} if first_region == "a" else {"b": b, "a": a}
    return Machine(
        {
            "id": "conflict",
            "initial": "running",
            "states": {
                "running": {
                    "type": "parallel",
                    "states": regions,
                }
            },
        }
    )


@pytest.mark.parametrize(
    ("first_region", "expected"),
    [
        ("a", {"running": {"a": "a2", "b": "b1"}}),
        ("b", {"running": {"a": "a1", "b": "b2"}}),
    ],
)
def test_parallel_conflicts_follow_document_order(first_region, expected):
    machine = _parallel_conflict_machine(first_region)

    state = machine.transition(machine.initial_state, "T")

    assert state.value == expected


def test_parallel_conflict_with_nested_target_reenters_sibling_initial_state():
    machine = Machine(
        {
            "id": "nested-conflict",
            "initial": "running",
            "states": {
                "running": {
                    "type": "parallel",
                    "states": {
                        "a": {
                            "initial": "a1",
                            "on": {"T": "#a22"},
                            "states": {
                                "a1": {
                                    "initial": "a11",
                                    "states": {"a11": {}, "a12": {}},
                                },
                                "a2": {
                                    "initial": "a21",
                                    "states": {
                                        "a21": {},
                                        "a22": {"id": "a22"},
                                    },
                                },
                            },
                        },
                        "b": {
                            "initial": "b1",
                            "states": {
                                "b1": {
                                    "initial": "b11",
                                    "states": {
                                        "b11": {"on": {"T": "b12"}},
                                        "b12": {},
                                    },
                                },
                                "b2": {},
                            },
                        },
                    },
                }
            },
        }
    )

    state = machine.transition(machine.initial_state, "T")

    assert state.value == {
        "running": {
            "a": {"a2": "a22"},
            "b": {"b1": "b11"},
        }
    }

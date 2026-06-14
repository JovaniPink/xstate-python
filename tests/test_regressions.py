"""Regression tests for engine bugs found in code review of the 0.2.0 work.

Each test here corresponds to a specific defect fixed after the PR #49
test-corpus port. They are intentionally minimal and named after the defect so
a future regression points straight at the cause.
"""

from xstate import Machine
from xstate.algorithm import get_child_states, get_proper_ancestors, is_history_state

# --- Fix #1: get_proper_ancestors must EXCLUDE state2 (the upper bound) -------
# Per W3C SCXML, getProperAncestors(s, ancestor) returns ancestors up to but not
# including `ancestor`. A regression here re-fires entry actions for the
# transition domain on every internal transition.


def test_get_proper_ancestors_excludes_upper_bound():
    machine = Machine(
        {
            "id": "r",
            "initial": "p",
            "states": {"p": {"initial": "c", "states": {"c": {}}}},
        }
    )
    p = machine.states["p"]
    c = p.states["c"]
    assert get_proper_ancestors(c, state2=p) == []
    # With no bound, all ancestors up to the root are returned.
    keys = [a.key for a in get_proper_ancestors(c, state2=None)]
    assert "p" in keys


# --- Fix #2: every parallel region advances via its own eventless transition --
# The old global `loop` flag stopped after the first region matched.


def test_parallel_regions_each_take_eventless_transition():
    machine = Machine(
        {
            "id": "p",
            "initial": "run",
            "states": {
                "run": {
                    "type": "parallel",
                    "states": {
                        "a": {
                            "initial": "a1",
                            "states": {"a1": {"on": {"": "a2"}}, "a2": {}},
                        },
                        "b": {
                            "initial": "b1",
                            "states": {"b1": {"on": {"": "b2"}}, "b2": {}},
                        },
                    },
                }
            },
        }
    )
    state = machine.initial_state
    assert state.value == {"run": {"a": "a2", "b": "b2"}}


# --- Fix #3: get_child_states excludes history pseudo-states -------------------
# A history child must not count as a (non-final) region, which would otherwise
# permanently block a parallel state's onDone.


def test_get_child_states_excludes_history():
    machine = Machine(
        {
            "id": "m",
            "initial": "on",
            "states": {
                "on": {
                    "initial": "a",
                    "states": {"a": {}, "h": {"type": "history", "id": "h"}},
                }
            },
        }
    )
    on = machine.states["on"]
    children = get_child_states(on)
    assert all(not is_history_state(c) for c in children)
    assert [c.key for c in children] == ["a"]


def test_parallel_on_done_fires_with_history_child_present():
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
                                "a1": {"on": {"FA": "a2"}},
                                "a2": {"type": "final"},
                                "ahist": {"type": "history", "id": "ahist"},
                            },
                        },
                        "b": {
                            "initial": "b1",
                            "states": {
                                "b1": {"on": {"FB": "b2"}},
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
    state = machine.transition(state, "FA")
    state = machine.transition(state, "FB")
    assert state.value == "done"


# --- Fix #4: a dict transition without "target" is an internal self-loop -------


def test_targetless_dict_transition_does_not_crash():
    machine = Machine(
        {
            "id": "m",
            "initial": "idle",
            "states": {"idle": {"on": {"PING": {"cond": lambda c, e: True}}}},
        }
    )
    state = machine.initial_state
    state = machine.transition(state, "PING")
    assert state.value == "idle"


# --- Fix #5 (with #1): deep history restores a 3-level-deep nested path --------
# Requires both get_proper_ancestors excluding state2 AND ancestor=state.parent
# so every intermediate ancestor between the restored atomic state and the
# history node's parent is entered.


def test_deep_history_restores_three_level_nested_path():
    machine = Machine(
        {
            "id": "d",
            "initial": "off",
            "states": {
                "off": {"on": {"POWER": "#dhist"}},
                "on": {
                    "initial": "a",
                    "on": {"POWER": "off"},
                    "states": {
                        "a": {
                            "initial": "a1",
                            "states": {
                                "a1": {"on": {"NEXT": "a2"}},
                                "a2": {
                                    "initial": "x",
                                    "states": {"x": {}},
                                },
                            },
                        },
                        "dhist": {
                            "type": "history",
                            "history": "deep",
                            "id": "dhist",
                        },
                    },
                },
            },
        }
    )
    state = machine.initial_state
    state = machine.transition(state, "POWER")  # on.a.a1
    state = machine.transition(state, "NEXT")  # on.a.a2.x
    assert state.value == {"on": {"a": {"a2": "x"}}}
    state = machine.transition(state, "POWER")  # off (deep history: x)
    state = machine.transition(state, "POWER")  # restore -> on.a.a2.x
    assert state.value == {"on": {"a": {"a2": "x"}}}

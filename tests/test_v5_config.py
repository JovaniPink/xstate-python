"""Tests for XState v5 config-alignment features (0.4.0).

- ``guard``  — v5 canonical name for ``cond``; both spellings accepted
- ``output`` — v5 canonical name for final-state ``data``; both spellings accepted
- ``always`` — v5 keyword for eventless (null-event) transitions
- ``MachineSnapshot`` — v5 public alias for ``State``; adds ``status``/``output``/``error``
- ``State.matches()`` — helper for checking nested state values
"""

import pytest
from xstate import Machine, assign, MachineSnapshot


# ---------------------------------------------------------------------------
# guard: v5 spelling of cond
# ---------------------------------------------------------------------------


def test_guard_accepted_as_transition_condition():
    """``guard`` keyword works identically to ``cond``."""
    machine = Machine(
        {
            "id": "g",
            "initial": "idle",
            "context": {"count": 5},
            "states": {
                "idle": {
                    "on": {
                        "CHECK": [
                            {
                                "target": "high",
                                "guard": lambda ctx, _: ctx["count"] > 3,
                            },
                            {"target": "low"},
                        ]
                    }
                },
                "high": {},
                "low": {},
            },
        }
    )
    state = machine.initial_state
    state = machine.transition(state, "CHECK")
    assert state.value == "high"


def test_guard_false_falls_through_to_next():
    machine = Machine(
        {
            "id": "g",
            "initial": "idle",
            "context": {"count": 1},
            "states": {
                "idle": {
                    "on": {
                        "CHECK": [
                            {
                                "target": "high",
                                "guard": lambda ctx, _: ctx["count"] > 3,
                            },
                            {"target": "low"},
                        ]
                    }
                },
                "high": {},
                "low": {},
            },
        }
    )
    state = machine.initial_state
    state = machine.transition(state, "CHECK")
    assert state.value == "low"


def test_cond_still_works_for_backwards_compat():
    """``cond`` continues to work as a backwards-compatible spelling."""
    machine = Machine(
        {
            "id": "g",
            "initial": "idle",
            "context": {"ok": True},
            "states": {
                "idle": {
                    "on": {
                        "GO": [
                            {"target": "yes", "cond": lambda ctx, _: ctx["ok"]},
                            {"target": "no"},
                        ]
                    }
                },
                "yes": {},
                "no": {},
            },
        }
    )
    state = machine.initial_state
    state = machine.transition(state, "GO")
    assert state.value == "yes"


def test_guard_takes_precedence_over_cond_when_both_present():
    """If both keys appear, ``guard`` wins."""
    machine = Machine(
        {
            "id": "g",
            "initial": "idle",
            "states": {
                "idle": {
                    "on": {
                        "GO": [
                            {
                                "target": "a",
                                "guard": lambda *_: True,
                                "cond": lambda *_: False,
                            },
                            {"target": "b"},
                        ]
                    }
                },
                "a": {},
                "b": {},
            },
        }
    )
    state = machine.initial_state
    state = machine.transition(state, "GO")
    assert state.value == "a"


def test_guard_as_named_string_resolves_from_machine_guards():
    machine = Machine(
        {
            "id": "g",
            "initial": "idle",
            "context": {"x": 10},
            "states": {
                "idle": {
                    "on": {
                        "GO": [
                            {"target": "big", "guard": "isBig"},
                            {"target": "small"},
                        ]
                    }
                },
                "big": {},
                "small": {},
            },
        },
        guards={"isBig": lambda ctx, _: ctx["x"] > 5},
    )
    state = machine.initial_state
    state = machine.transition(state, "GO")
    assert state.value == "big"


# ---------------------------------------------------------------------------
# output: v5 spelling of final-state data
# ---------------------------------------------------------------------------


def test_output_on_final_state_reaches_on_done():
    machine = Machine(
        {
            "id": "o",
            "initial": "work",
            "context": {"result": None},
            "states": {
                "work": {
                    "initial": "task",
                    "states": {
                        "task": {"type": "final", "output": {"value": 99}}
                    },
                    "onDone": {
                        "target": "done",
                        "actions": [assign({"result": lambda ctx, ev: ev.data["value"]})],
                    },
                },
                "done": {},
            },
        }
    )
    state = machine.initial_state
    assert state.value == "done"
    assert state.context["result"] == 99


def test_data_still_works_for_backwards_compat():
    machine = Machine(
        {
            "id": "o",
            "initial": "work",
            "context": {"result": None},
            "states": {
                "work": {
                    "initial": "task",
                    "states": {
                        "task": {"type": "final", "data": {"value": 42}}
                    },
                    "onDone": {
                        "target": "done",
                        "actions": [assign({"result": lambda ctx, ev: ev.data["value"]})],
                    },
                },
                "done": {},
            },
        }
    )
    state = machine.initial_state
    assert state.value == "done"
    assert state.context["result"] == 42


# ---------------------------------------------------------------------------
# always: v5 eventless transitions
# ---------------------------------------------------------------------------


def test_always_fires_on_entry():
    """``always`` transitions fire immediately when entered, like on: {'': ...}."""
    machine = Machine(
        {
            "id": "a",
            "initial": "start",
            "states": {
                "start": {"always": "done"},
                "done": {},
            },
        }
    )
    state = machine.initial_state
    assert state.value == "done"


def test_always_with_guard_fires_when_condition_met():
    machine = Machine(
        {
            "id": "a",
            "initial": "check",
            "context": {"ready": True},
            "states": {
                "check": {
                    "always": [
                        {
                            "target": "ready",
                            "guard": lambda ctx, _: ctx["ready"],
                        },
                        {"target": "waiting"},
                    ]
                },
                "ready": {},
                "waiting": {},
            },
        }
    )
    state = machine.initial_state
    assert state.value == "ready"


def test_always_guard_false_falls_through():
    machine = Machine(
        {
            "id": "a",
            "initial": "check",
            "context": {"ready": False},
            "states": {
                "check": {
                    "always": [
                        {
                            "target": "ready",
                            "guard": lambda ctx, _: ctx["ready"],
                        },
                        {"target": "waiting"},
                    ]
                },
                "ready": {},
                "waiting": {},
            },
        }
    )
    state = machine.initial_state
    assert state.value == "waiting"


def test_always_fires_after_event_transition():
    """An ``always`` transition fires automatically after an event-triggered entry."""
    machine = Machine(
        {
            "id": "a",
            "initial": "idle",
            "states": {
                "idle": {"on": {"GO": "intermediate"}},
                "intermediate": {"always": "final"},
                "final": {},
            },
        }
    )
    state = machine.initial_state
    state = machine.transition(state, "GO")
    assert state.value == "final"


def test_always_and_on_coexist():
    """``always`` and ``on`` can both be present; events still work normally."""
    machine = Machine(
        {
            "id": "a",
            "initial": "idle",
            "context": {"skip": False},
            "states": {
                "idle": {
                    "always": [
                        {
                            "target": "skipped",
                            "guard": lambda ctx, _: ctx["skip"],
                        }
                    ],
                    "on": {"NEXT": "active"},
                },
                "active": {},
                "skipped": {},
            },
        }
    )
    state = machine.initial_state
    # always guard is false, so we stay in idle
    assert state.value == "idle"
    state = machine.transition(state, "NEXT")
    assert state.value == "active"


# ---------------------------------------------------------------------------
# MachineSnapshot / State.status / State.output / State.matches
# ---------------------------------------------------------------------------


def test_machine_snapshot_is_state_alias():
    from xstate.state import State

    assert MachineSnapshot is State


def test_status_active_for_running_machine():
    machine = Machine(
        {"id": "s", "initial": "running", "states": {"running": {}, "done": {}}}
    )
    state = machine.initial_state
    assert state.status == "active"
    assert state.output is None
    assert state.error is None


def test_status_done_when_final_state_reached():
    machine = Machine(
        {
            "id": "s",
            "initial": "running",
            "states": {
                "running": {"on": {"FINISH": "done"}},
                "done": {"type": "final"},
            },
        }
    )
    state = machine.initial_state
    state = machine.transition(state, "FINISH")
    assert state.status == "done"


def test_output_populated_from_final_state_output():
    machine = Machine(
        {
            "id": "s",
            "initial": "running",
            "states": {
                "running": {"on": {"FINISH": "done"}},
                "done": {"type": "final", "output": {"score": 100}},
            },
        }
    )
    state = machine.initial_state
    state = machine.transition(state, "FINISH")
    assert state.status == "done"
    assert state.output == {"score": 100}


def test_output_none_when_final_state_has_no_output():
    machine = Machine(
        {
            "id": "s",
            "initial": "a",
            "states": {
                "a": {"on": {"DONE": "b"}},
                "b": {"type": "final"},
            },
        }
    )
    state = machine.initial_state
    state = machine.transition(state, "DONE")
    assert state.status == "done"
    assert state.output is None


def test_matches_string_value():
    machine = Machine(
        {"id": "m", "initial": "idle", "states": {"idle": {}, "active": {}}}
    )
    state = machine.initial_state
    assert state.matches("idle")
    assert not state.matches("active")


def test_matches_nested_dict_value():
    machine = Machine(
        {
            "id": "m",
            "initial": "loading",
            "states": {
                "loading": {
                    "initial": "data",
                    "states": {"data": {}, "meta": {}},
                },
                "done": {},
            },
        }
    )
    state = machine.initial_state
    assert state.matches({"loading": "data"})
    assert not state.matches({"loading": "meta"})
    assert not state.matches("done")

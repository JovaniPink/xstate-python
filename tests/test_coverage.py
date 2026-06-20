"""Targeted tests for branches not reached by the primary test suite.

Each section is annotated with the source file and lines it covers.
"""

import threading

import pytest

from xstate import Machine, SimulatedClock, ThreadClock, interpret, send, send_to
from xstate.action import Action, build_action
from xstate.algorithm import _apply_assignment, _invoke
from xstate.event import Event, to_event

# ---------------------------------------------------------------------------
# event.py — to_event() normalisation
# ---------------------------------------------------------------------------


def test_to_event_passthrough():
    ev = Event("TEST")
    assert to_event(ev) is ev


def test_to_event_from_str():
    ev = to_event("FOO")
    assert ev.name == "FOO"
    assert ev.data is None


def test_to_event_from_dict():
    ev = to_event({"type": "FOO", "x": 1})
    assert ev.name == "FOO"
    assert ev.data == {"type": "FOO", "x": 1}


def test_to_event_fallback_str_coercion():
    # event.py:21 — non-str/dict/Event input falls back to str(event)
    ev = to_event(42)
    assert ev.name == "42"


# ---------------------------------------------------------------------------
# action.py — repr and build_action fallback
# ---------------------------------------------------------------------------


def test_action_repr_constructor_style():
    # action.py:34
    a = Action("my_action")
    assert repr(a) == "Action(type='my_action')"


def test_build_action_non_standard_type():
    # action.py:64 — last fallback: Action(str(raw))
    a = build_action(99)
    assert a.type == "99"


# ---------------------------------------------------------------------------
# algorithm.py — _invoke arity dispatch
# ---------------------------------------------------------------------------


def test_invoke_zero_arg_function():
    # algorithm.py:57 — len(positional) == 0
    def always_true():
        return True

    assert _invoke(always_true, {"x": 1}, Event("E")) is True


def test_invoke_one_arg_function():
    # algorithm.py:59 — len(positional) == 1
    def double(ctx):
        return ctx["x"] * 2

    assert _invoke(double, {"x": 3}, Event("E")) == 6


def test_apply_assignment_with_none_context():
    # algorithm.py:66 — early return when context is None
    action = Action("xstate.assign", data={"assignment": {"x": 1}})
    _apply_assignment(action, None, None)  # must not raise


def test_invoke_zero_arg_guard_via_machine():
    # Zero-arg guard resolved through a full machine transition
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "states": {
                "a": {"on": {"GO": {"target": "b", "guard": "always_true"}}},
                "b": {},
            },
        },
        guards={"always_true": lambda: True},
    )
    state = machine.transition(machine.initial_state, "GO")
    assert state.value == "b"


# ---------------------------------------------------------------------------
# state.py — matches() dict pattern and non-standard inputs
# ---------------------------------------------------------------------------


def _compound_machine():
    return Machine(
        {
            "id": "m",
            "initial": "loading",
            "states": {
                "loading": {
                    "initial": "data",
                    "states": {
                        "data": {},
                        "error": {},
                    },
                },
                "idle": {},
            },
        }
    )


def test_state_matches_dict_pattern_true():
    # state.py:96, 99, 109 — _matches_dict with nested compound value
    state = _compound_machine().initial_state
    assert state.matches({"loading": "data"})


def test_state_matches_dict_pattern_false():
    state = _compound_machine().initial_state
    assert not state.matches({"loading": "error"})


def test_state_matches_non_str_non_dict_returns_false():
    # state.py:99 else branch
    machine = Machine({"id": "m", "initial": "a", "states": {"a": {}}})
    assert machine.initial_state.matches(42) is False


def test_state_can_with_dict_event():
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "states": {
                "a": {"on": {"GO": "b"}},
                "b": {},
            },
        }
    )
    state = machine.initial_state
    assert state.can({"type": "GO"}) is True
    assert state.can({"type": "NOPE"}) is False


def test_state_repr_constructor_style():
    machine = Machine({"id": "m", "initial": "a", "states": {"a": {}}})
    r = repr(machine.initial_state)
    assert r.startswith("State(value=")
    assert "status=" in r


# ---------------------------------------------------------------------------
# machine.py — state_from() with nested dict value
# ---------------------------------------------------------------------------


def test_machine_state_from_nested_dict():
    # machine.py:146 — _get_configuration with dict state value
    machine = _compound_machine()
    state = machine.state_from({"loading": "data"})
    assert state.value == {"loading": "data"}


# ---------------------------------------------------------------------------
# state_node.py — initial property ValueError paths
# ---------------------------------------------------------------------------


def test_state_node_initial_invalid_key_raises():
    with pytest.raises(ValueError, match="Initial state 'nonexistent'"):
        Machine(
            {
                "id": "m",
                "initial": "nonexistent",
                "states": {"a": {}, "b": {}},
            }
        )


def test_state_node_get_relative_missing_sibling():
    with pytest.raises(ValueError, match="typo_state"):
        Machine(
            {
                "id": "m",
                "initial": "a",
                "states": {
                    "a": {"on": {"GO": "typo_state"}},
                    "b": {},
                },
            }
        )


def test_state_node_get_relative_missing_id():
    with pytest.raises(ValueError, match="No state with id 'no-such-id'"):
        Machine(
            {
                "id": "m",
                "initial": "a",
                "states": {
                    "a": {"on": {"GO": "#no-such-id"}},
                    "b": {},
                },
            }
        )


# ---------------------------------------------------------------------------
# interpreter.py — start with explicit initial_state, stop with timers
# ---------------------------------------------------------------------------


def test_interpreter_start_with_explicit_initial_state():
    # interpreter.py:91
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "states": {
                "a": {"on": {"GO": "b"}},
                "b": {},
            },
        }
    )
    b_state = machine.transition(machine.initial_state, "GO")
    service = interpret(machine).start(initial_state=b_state)
    assert service.state.value == "b"


def test_interpreter_stop_cancels_after_timer():
    # interpreter.py:100-102 — stop() drains _scheduled (after: timers)
    clock = SimulatedClock()
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "states": {
                "a": {"after": {500: "b"}},
                "b": {},
            },
        }
    )
    service = interpret(machine, clock=clock).start()
    assert service.state.value == "a"
    service.stop()
    clock.increment(1000)  # timer was cancelled; state stays "a"
    assert service.state.value == "a"


def test_interpreter_stop_cancels_delayed_send():
    # interpreter.py:103-105 — stop() drains _send_timers
    clock = SimulatedClock()
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "states": {
                "a": {
                    "entry": [send("TICK", delay=500, id="t1")],
                    "on": {"TICK": "b"},
                },
                "b": {},
            },
        }
    )
    service = interpret(machine, clock=clock).start()
    service.stop()
    clock.increment(1000)  # delayed send was cancelled
    assert service.state.value == "a"


def test_interpreter_send_to_without_actor_is_noop():
    # interpreter.py:208-209 — _execute_send_to when _actor is None
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "states": {
                "a": {
                    "on": {
                        "GO": {
                            "target": "b",
                            "actions": [send_to("logger", "LOG")],
                        }
                    }
                },
                "b": {},
            },
        }
    )
    service = interpret(machine).start()
    service.send("GO")  # send_to silently dropped; transition still happens
    assert service.state.value == "b"


# ---------------------------------------------------------------------------
# transition.py — Transition repr
# ---------------------------------------------------------------------------


def test_transition_repr():
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "states": {"a": {"on": {"GO": "b"}}, "b": {}},
        }
    )
    node = machine.root.states["a"]
    t = node.transitions[0]
    r = repr(t)
    assert "Transition(" in r
    assert "event='GO'" in r


# ---------------------------------------------------------------------------
# scheduler.py — SimulatedClock.now() and ThreadClock
# ---------------------------------------------------------------------------


def test_simulated_clock_now():
    # scheduler.py:51
    clock = SimulatedClock()
    assert clock.now() == 0.0
    clock.increment(250)
    assert clock.now() == 250.0
    clock.increment(750)
    assert clock.now() == 1000.0


def test_thread_clock_fires_callback():
    # scheduler.py:81-97 — ThreadClock.set_timeout fires after delay
    clock = ThreadClock()
    fired = threading.Event()
    clock.set_timeout(fired.set, 30)  # 30 ms
    assert fired.wait(timeout=3.0), "ThreadClock timer did not fire"


def test_thread_clock_clear_cancels_callback():
    # scheduler.py:100-103 — clear_timeout prevents the callback from firing
    clock = ThreadClock()
    fired = threading.Event()
    tid = clock.set_timeout(fired.set, 80)  # 80 ms
    clock.clear_timeout(tid)
    assert not fired.wait(timeout=0.3), "ThreadClock fired after clear_timeout"


def test_thread_clock_clear_nonexistent_is_noop():
    clock = ThreadClock()
    clock.clear_timeout(9999)  # must not raise


# ---------------------------------------------------------------------------
# state.py — _matches_dict return-False branch
# ---------------------------------------------------------------------------


def test_matches_dict_nested_pattern_on_atomic_value_returns_false():
    # state.py:109 — pattern is dict but state_value[key] is a str (atomic), not dict
    state = _compound_machine().initial_state
    # "loading" child is "data" (atomic string), not a further nested compound
    assert not state.matches({"loading": {"deeper": "nested"}})


# ---------------------------------------------------------------------------
# machine.py — _get_configuration with invalid state name
# ---------------------------------------------------------------------------


def test_machine_state_from_invalid_name_raises():
    # machine.py:148
    machine = Machine({"id": "m", "initial": "a", "states": {"a": {}}})
    with pytest.raises(ValueError, match="State node 'bad' is missing"):
        machine.state_from("bad")


# ---------------------------------------------------------------------------
# state_node.py — additional StateNode paths
# ---------------------------------------------------------------------------


def test_state_node_initial_auto_selects_first_child():
    # state_node.py:232 — compound child with no explicit "initial" key
    machine = Machine(
        {
            "id": "m",
            "initial": "outer",
            "states": {
                "outer": {
                    # no "initial" key — first child is auto-selected
                    "states": {"first": {}, "second": {}},
                },
            },
        }
    )
    state = machine.initial_state
    assert state.value == {"outer": "first"}


def test_state_node_initial_on_atomic_raises():
    # state_node.py:239 — calling .initial on an atomic node raises
    machine = Machine({"id": "m", "initial": "a", "states": {"a": {}}})
    a_node = machine.root.states["a"]
    with pytest.raises(ValueError, match="has no initial state"):
        _ = a_node.initial


def test_state_node_get_relative_from_root_resolves_child():
    # Root-level transitions can target child states by key after parser resolution.
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "on": {"RESET": "a"},  # machine-level transition to relative name
            "states": {"a": {}, "b": {}},
        }
    )
    state = machine.transition(machine.initial_state, "RESET")
    assert state.value == "a"


def test_state_node_repr():
    # state_node.py:275
    machine = Machine({"id": "m", "initial": "a", "states": {"a": {}}})
    r = repr(machine.root.states["a"])
    assert "StateNode" in r


def test_history_state_with_explicit_default_target():
    # state_node.py:110 — history state with a configured default "target"
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "states": {
                "a": {
                    "initial": "a1",
                    "states": {
                        "a1": {"on": {"NEXT": "a2"}},
                        "a2": {},
                        "hist": {
                            "type": "history",
                            "target": "a1",  # explicit default target
                        },
                    },
                    "on": {"OUT": "b"},
                },
                "b": {"on": {"BACK": {"target": "#m.a.hist"}}},
            },
        }
    )
    # First time history has no recording — default target "a1" should be used
    s = machine.initial_state
    s = machine.transition(s, "OUT")
    assert s.value == "b"
    s = machine.transition(s, "BACK")
    assert s.value == {"a": "a1"}

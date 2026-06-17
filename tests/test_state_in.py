"""Tests for `in`-state guards on transitions (0.2.0).

An `in` guard on a transition makes it conditional on the machine currently
being in a specific (sub)state.  Three matching forms are supported:

  * dict   ``{"b": "b2"}``          — parent.key == "b" and child.key == "b2"
  * string ``"b.b2"``               — same, dotted path
  * string ``"#id"``                — any active state with that id

Based on the XState v4 statein.test.ts describe block.
"""

from xstate import Machine

# ---------------------------------------------------------------------------
# Machine: parallel root with two regions that have cross-region `in` guards
# ---------------------------------------------------------------------------
#
# Region A (initial a1):
#   a1 --EVENT_DICT-->  a2   only if b is in b2   (dict form)
#   a1 --EVENT_STR-->   a2   only if b is in b2   (dotted-string form)
#   a1 --EVENT_ID-->    a2   only if b is in b2   (#id form)
#
# Region B (initial b1):
#   b1 --GO_B2--> b2   (unconditional, used to set up state)


def make_cross_region():
    return Machine(
        {
            "id": "cross",
            "type": "parallel",
            "states": {
                "a": {
                    "initial": "a1",
                    "states": {
                        "a1": {
                            "on": {
                                "EVENT_DICT": {"target": "a2", "in": {"b": "b2"}},
                                "EVENT_STR": {"target": "a2", "in": "b.b2"},
                                "EVENT_ID": {
                                    "target": "a2",
                                    "in": "#cross.b.b2",
                                },
                            }
                        },
                        "a2": {},
                    },
                },
                "b": {
                    "initial": "b1",
                    "states": {
                        "b1": {"on": {"GO_B2": "b2"}},
                        "b2": {},
                    },
                },
            },
        }
    )


# -- dict form ---------------------------------------------------------------


def test_in_dict_fires_when_condition_met():
    """Transition fires when the `in` dict condition is satisfied."""
    machine = make_cross_region()
    state = machine.initial_state
    assert state.value == {"a": "a1", "b": "b1"}
    state = machine.transition(state, "GO_B2")  # b → b2
    assert state.value == {"a": "a1", "b": "b2"}
    state = machine.transition(state, "EVENT_DICT")  # a1→a2 because b==b2
    assert state.value == {"a": "a2", "b": "b2"}


def test_in_dict_blocks_when_condition_not_met():
    """Transition is blocked when the `in` dict condition is not satisfied."""
    machine = make_cross_region()
    state = machine.initial_state  # a=a1, b=b1
    state = machine.transition(state, "EVENT_DICT")  # b≠b2 → no-op
    assert state.value == {"a": "a1", "b": "b1"}


# -- dotted-string form -------------------------------------------------------


def test_in_str_fires_when_condition_met():
    """Transition fires when the `in` dotted-string condition is satisfied."""
    machine = make_cross_region()
    state = machine.initial_state
    state = machine.transition(state, "GO_B2")
    state = machine.transition(state, "EVENT_STR")
    assert state.value == {"a": "a2", "b": "b2"}


def test_in_str_blocks_when_condition_not_met():
    """Transition is blocked when the `in` dotted-string condition fails."""
    machine = make_cross_region()
    state = machine.initial_state
    state = machine.transition(state, "EVENT_STR")
    assert state.value == {"a": "a1", "b": "b1"}


# -- #id form ----------------------------------------------------------------


def test_in_id_fires_when_condition_met():
    """Transition fires when the `in` #id condition is satisfied."""
    machine = make_cross_region()
    state = machine.initial_state
    state = machine.transition(state, "GO_B2")
    state = machine.transition(state, "EVENT_ID")
    assert state.value == {"a": "a2", "b": "b2"}


def test_in_id_blocks_when_condition_not_met():
    """Transition is blocked when the `in` #id condition fails."""
    machine = make_cross_region()
    state = machine.initial_state
    state = machine.transition(state, "EVENT_ID")
    assert state.value == {"a": "a1", "b": "b1"}


# ---------------------------------------------------------------------------
# Machine: compound state with `in` guard restricting compound-child access
# ---------------------------------------------------------------------------
#
# red has substates walk/wait/stop.
# red --TIMER--> green   ONLY if red is in "stop" (in: {red: "stop"})
#
# This is the classic traffic-light "forbid early green" example from XState docs.


def make_traffic_light():
    return Machine(
        {
            "id": "light",
            "initial": "green",
            "states": {
                "green": {"on": {"TIMER": "yellow"}},
                "yellow": {"on": {"TIMER": "red"}},
                "red": {
                    "initial": "walk",
                    "states": {
                        "walk": {"on": {"STEP": "wait"}},
                        "wait": {"on": {"STEP": "stop"}},
                        "stop": {},
                    },
                    "on": {
                        "TIMER": [
                            {"target": "green", "in": {"red": "stop"}},
                        ]
                    },
                },
            },
        }
    )


def test_traffic_light_blocked_at_walk():
    """TIMER from red.walk is blocked — 'in {red: stop}' is not satisfied."""
    machine = make_traffic_light()
    state = machine.initial_state
    state = machine.transition(state, "TIMER")  # green → yellow
    state = machine.transition(state, "TIMER")  # yellow → red (walk)
    assert state.value == {"red": "walk"}
    state = machine.transition(state, "TIMER")  # no-op (in: red.stop not met)
    assert state.value == {"red": "walk"}


def test_traffic_light_blocked_at_wait():
    """TIMER from red.wait is also blocked."""
    machine = make_traffic_light()
    state = machine.initial_state
    state = machine.transition(state, "TIMER")  # → yellow
    state = machine.transition(state, "TIMER")  # → red.walk
    state = machine.transition(state, "STEP")  # → red.wait
    assert state.value == {"red": "wait"}
    state = machine.transition(state, "TIMER")  # no-op
    assert state.value == {"red": "wait"}


def test_traffic_light_fires_from_stop():
    """TIMER from red.stop fires because 'in {red: stop}' IS satisfied."""
    machine = make_traffic_light()
    state = machine.initial_state
    state = machine.transition(state, "TIMER")  # → yellow
    state = machine.transition(state, "TIMER")  # → red.walk
    state = machine.transition(state, "STEP")  # → red.wait
    state = machine.transition(state, "STEP")  # → red.stop
    assert state.value == {"red": "stop"}
    state = machine.transition(state, "TIMER")  # guard satisfied → green
    assert state.value == "green"


# ---------------------------------------------------------------------------
# `in` combined with `cond`
# ---------------------------------------------------------------------------
#
# Both the `in` guard AND the `cond` must be true for the transition to fire.


def make_combined():
    return Machine(
        {
            "id": "combined",
            "type": "parallel",
            "states": {
                "a": {
                    "initial": "a1",
                    "states": {
                        "a1": {
                            "on": {
                                "GO": {
                                    "target": "a2",
                                    "in": {"b": "b2"},
                                    "guard": lambda ctx, _: ctx.get("allowed", False),
                                }
                            }
                        },
                        "a2": {},
                    },
                },
                "b": {
                    "initial": "b1",
                    "states": {
                        "b1": {"on": {"GO_B2": "b2"}},
                        "b2": {},
                    },
                },
            },
        },
        context={"allowed": False},
    )


def test_combined_both_must_pass():
    """Transition fires only when both `in` and `cond` are satisfied."""
    machine = Machine(
        {
            "id": "combo",
            "type": "parallel",
            "states": {
                "a": {
                    "initial": "a1",
                    "states": {
                        "a1": {
                            "on": {
                                "GO": {
                                    "target": "a2",
                                    "in": {"b": "b2"},
                                    "guard": lambda ctx, _: ctx.get("ok", False),
                                }
                            }
                        },
                        "a2": {},
                    },
                },
                "b": {
                    "initial": "b1",
                    "states": {"b1": {"on": {"GO_B2": "b2"}}, "b2": {}},
                },
            },
            "context": {"ok": True},
        }
    )
    state = machine.initial_state  # a=a1, b=b1; ctx.ok=True
    state = machine.transition(state, "GO")  # in fails (b≠b2)
    assert state.value == {"a": "a1", "b": "b1"}
    state = machine.transition(state, "GO_B2")  # b→b2
    state = machine.transition(state, "GO")  # in ✓, cond ✓ → a2
    assert state.value == {"a": "a2", "b": "b2"}

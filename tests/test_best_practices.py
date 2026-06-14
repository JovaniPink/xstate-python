"""Regression tests for best-practice fixes applied to the core engine.

Covers:
  - Named assign in the actions registry works end-to-end
  - Mutable default argument guard: separate Machine instances don't share dicts
  - Shallow-copy fix: initial_state deep-copies nested context
  - Friendly ValueError when machine config has no 'id'
  - UserWarning when a named action has no implementation
"""

import warnings

import pytest

from xstate import Machine, assign


# ---------------------------------------------------------------------------
# Named assign in actions registry
# ---------------------------------------------------------------------------


def test_named_assign_in_registry():
    """Machine(config, actions={'save': assign({...})}) must update context."""
    machine = Machine(
        {
            "id": "counter",
            "context": {"count": 0},
            "initial": "idle",
            "states": {
                "idle": {
                    "on": {
                        "INC": {
                            "actions": ["increment"],
                        }
                    }
                }
            },
        },
        actions={"increment": assign({"count": lambda c, e: c["count"] + 1})},
    )
    state = machine.initial_state
    state = machine.transition(state, "INC")
    assert state.context["count"] == 1
    state = machine.transition(state, "INC")
    assert state.context["count"] == 2


def test_named_assign_with_callable_assignment():
    """Named assign using a whole-context callable (not a dict of fields)."""
    machine = Machine(
        {
            "id": "doubler",
            "context": {"n": 3},
            "initial": "a",
            "states": {
                "a": {"on": {"GO": {"target": "b", "actions": ["doubleN"]}}},
                "b": {},
            },
        },
        actions={"doubleN": assign(lambda c, e: {"n": c["n"] * 2})},
    )
    state = machine.transition(machine.initial_state, "GO")
    assert state.context["n"] == 6


def test_named_assign_on_entry():
    """Named assign in an entry action fires on entering the state."""
    machine = Machine(
        {
            "id": "entry_assign",
            "context": {"visited": False},
            "initial": "a",
            "states": {
                "a": {"on": {"GO": "b"}},
                "b": {"entry": ["markVisited"]},
            },
        },
        actions={"markVisited": assign({"visited": True})},
    )
    state = machine.transition(machine.initial_state, "GO")
    assert state.context["visited"] is True


# ---------------------------------------------------------------------------
# Mutable default argument guard
# ---------------------------------------------------------------------------


def test_separate_machines_dont_share_registries():
    """Two Machine() calls without explicit registries must not share dicts."""
    m1 = Machine({"id": "m1", "initial": "a", "states": {"a": {}}})
    m2 = Machine({"id": "m2", "initial": "a", "states": {"a": {}}})
    m1.actions["foo"] = lambda: None
    assert "foo" not in m2.actions


def test_separate_states_dont_share_actions_list():
    """Two State objects from the same machine must not share an actions list."""
    machine = Machine(
        {
            "id": "s",
            "initial": "a",
            "states": {"a": {}, "b": {}},
        }
    )
    s1 = machine.initial_state
    s2 = machine.transition(s1, "NOOP")  # no transition — returns same state shape
    # Mutating one actions list must not corrupt the other.
    s1.actions.append("sentinel")
    assert "sentinel" not in s2.actions


# ---------------------------------------------------------------------------
# Deep context copy on initial_state
# ---------------------------------------------------------------------------


def test_initial_state_deep_copies_nested_context():
    """initial_state must deep-copy nested mutable context so instances are isolated."""
    machine = Machine(
        {
            "id": "nested",
            "context": {"data": {"value": 1}},
            "initial": "a",
            "states": {"a": {}},
        }
    )
    s1 = machine.initial_state
    s2 = machine.initial_state
    s1.context["data"]["value"] = 99
    assert s2.context["data"]["value"] == 1


# ---------------------------------------------------------------------------
# Friendly error for missing 'id'
# ---------------------------------------------------------------------------


def test_machine_without_id_raises_value_error():
    with pytest.raises(ValueError, match="'id'"):
        Machine({"initial": "a", "states": {"a": {}}})


# ---------------------------------------------------------------------------
# Warning for unknown action names
# ---------------------------------------------------------------------------


def test_unknown_action_name_emits_warning():
    machine = Machine(
        {
            "id": "w",
            "initial": "a",
            "states": {
                "a": {"on": {"GO": {"target": "b", "actions": ["missing"]}}},
                "b": {},
            },
        }
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        machine.transition(machine.initial_state, "GO")
    assert any("missing" in str(w.message) for w in caught)
    assert any(issubclass(w.category, UserWarning) for w in caught)

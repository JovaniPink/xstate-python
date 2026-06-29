"""Tests for state tags + has_tag()/hasTag() (0.7.0).

XState v5 lets a state declare ``tags: ["loading"]`` and query the running
snapshot with ``state.hasTag("loading")``.  Tags aggregate across the whole
active configuration (compound ancestors + parallel regions).
"""

import pytest

from xstate import Machine, create_actor
from xstate.exceptions import InvalidConfigError

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_tags_as_list():
    machine = Machine(
        {
            "id": "m",
            "initial": "loading",
            "states": {
                "loading": {"tags": ["busy", "network"]},
                "idle": {},
            },
        }
    )
    assert machine.initial_state.tags == frozenset({"busy", "network"})


def test_tags_as_single_string():
    machine = Machine(
        {
            "id": "m",
            "initial": "loading",
            "states": {
                "loading": {"tags": "busy"},
                "idle": {},
            },
        }
    )
    assert machine.initial_state.tags == frozenset({"busy"})


def test_no_tags_is_empty_frozenset():
    machine = Machine({"id": "m", "initial": "idle", "states": {"idle": {}}})
    assert machine.initial_state.tags == frozenset()


def test_non_string_tag_raises():
    with pytest.raises(InvalidConfigError, match="every tag must be a string"):
        Machine(
            {
                "id": "m",
                "initial": "a",
                "states": {"a": {"tags": ["ok", 123]}},
            }
        )


def test_invalid_tags_type_raises():
    with pytest.raises(InvalidConfigError, match="must be a string or a list"):
        Machine(
            {
                "id": "m",
                "initial": "a",
                "states": {"a": {"tags": {"not": "valid"}}},
            }
        )


# ---------------------------------------------------------------------------
# has_tag / hasTag query
# ---------------------------------------------------------------------------


def test_has_tag_true():
    machine = Machine(
        {
            "id": "m",
            "initial": "loading",
            "states": {"loading": {"tags": ["busy"]}, "idle": {}},
        }
    )
    assert machine.initial_state.has_tag("busy") is True


def test_has_tag_false():
    machine = Machine(
        {
            "id": "m",
            "initial": "loading",
            "states": {"loading": {"tags": ["busy"]}, "idle": {}},
        }
    )
    assert machine.initial_state.has_tag("idle") is False


def test_hasTag_camelcase_alias():
    machine = Machine(
        {
            "id": "m",
            "initial": "loading",
            "states": {"loading": {"tags": ["busy"]}, "idle": {}},
        }
    )
    assert machine.initial_state.hasTag("busy") is True
    assert machine.initial_state.hasTag("nope") is False


# ---------------------------------------------------------------------------
# Tags update across transitions
# ---------------------------------------------------------------------------


def test_tags_change_on_transition():
    machine = Machine(
        {
            "id": "m",
            "initial": "loading",
            "states": {
                "loading": {"tags": ["busy"], "on": {"DONE": "ready"}},
                "ready": {"tags": ["interactive"]},
            },
        }
    )
    state = machine.initial_state
    assert state.has_tag("busy")

    state = machine.transition(state, "DONE")
    assert state.has_tag("interactive")
    assert not state.has_tag("busy")


def test_tags_via_actor():
    machine = Machine(
        {
            "id": "m",
            "initial": "loading",
            "states": {
                "loading": {"tags": ["busy"], "on": {"DONE": "ready"}},
                "ready": {},
            },
        }
    )
    actor = create_actor(machine).start()
    assert actor.get_snapshot().has_tag("busy")
    actor.send("DONE")
    assert not actor.get_snapshot().has_tag("busy")


# ---------------------------------------------------------------------------
# Aggregation across compound ancestors and parallel regions
# ---------------------------------------------------------------------------


def test_tags_aggregate_from_compound_ancestor():
    machine = Machine(
        {
            "id": "m",
            "initial": "parent",
            "states": {
                "parent": {
                    "tags": ["outer"],
                    "initial": "child",
                    "states": {
                        "child": {"tags": ["inner"]},
                    },
                },
            },
        }
    )
    state = machine.initial_state
    # Both the active compound ancestor and the leaf contribute tags.
    assert state.tags == frozenset({"outer", "inner"})
    assert state.has_tag("outer")
    assert state.has_tag("inner")


def test_tags_aggregate_across_parallel_regions():
    machine = Machine(
        {
            "id": "m",
            "type": "parallel",
            "states": {
                "a": {
                    "initial": "a1",
                    "states": {"a1": {"tags": ["region-a"]}},
                },
                "b": {
                    "initial": "b1",
                    "states": {"b1": {"tags": ["region-b"]}},
                },
            },
        }
    )
    state = machine.initial_state
    assert state.has_tag("region-a")
    assert state.has_tag("region-b")
    assert {"region-a", "region-b"} <= state.tags

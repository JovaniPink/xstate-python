from types import MappingProxyType

import pytest

from xstate import Machine, and_, state_in, stateIn
from xstate.exceptions import InvalidConfigError


def test_state_tags_include_active_ancestors_and_leaf_nodes():
    machine = Machine(
        {
            "id": "checkout",
            "tags": ["app"],
            "initial": "cart",
            "states": {
                "cart": {
                    "tags": ["shopping"],
                    "initial": "editing",
                    "states": {
                        "editing": {"tags": ["editable"]},
                        "review": {"tags": ["reviewing"]},
                    },
                },
                "paid": {"tags": ["done"]},
            },
        }
    )

    state = machine.initial_state

    assert state.tags == frozenset({"app", "shopping", "editable"})
    assert state.has_tag("shopping")
    assert state.hasTag("editable")
    assert not state.has_tag("done")


def test_state_tags_are_immutable():
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "states": {"a": {"tags": ["active"]}},
        }
    )

    state = machine.initial_state

    with pytest.raises(AttributeError):
        state.tags.add("other")  # type: ignore[attr-defined]


def test_state_meta_exposes_active_state_metadata_read_only():
    machine = Machine(
        {
            "id": "doc",
            "meta": {"title": "Document workflow"},
            "initial": "editing",
            "states": {
                "editing": {"meta": {"label": "Editing"}},
                "published": {"meta": {"label": "Published"}},
            },
        }
    )

    state = machine.initial_state

    assert isinstance(state.meta, MappingProxyType)
    assert state.meta == {
        "doc": {"title": "Document workflow"},
        "doc.editing": {"label": "Editing"},
    }
    with pytest.raises(TypeError):
        state.meta["doc.published"] = {"label": "Published"}  # type: ignore[index]


def test_invalid_tags_are_path_aware():
    with pytest.raises(InvalidConfigError, match=r"states\.a\.tags\[0\]"):
        Machine(
            {
                "id": "m",
                "initial": "a",
                "states": {"a": {"tags": [object()]}},
            }
        )


def _parallel_machine_with_guard(guard):
    return Machine(
        {
            "id": "cross",
            "type": "parallel",
            "states": {
                "a": {
                    "initial": "a1",
                    "states": {
                        "a1": {"on": {"GO": {"target": "a2", "guard": guard}}},
                        "a2": {},
                    },
                },
                "b": {
                    "initial": "b1",
                    "states": {
                        "b1": {"on": {"GO_B2": "b2"}},
                        "b2": {"id": "ready"},
                    },
                },
            },
        }
    )


def test_state_in_guard_matches_dotted_path():
    machine = _parallel_machine_with_guard(state_in("b.b2"))
    state = machine.initial_state

    assert machine.transition(state, "GO").value == {"a": "a1", "b": "b1"}

    state = machine.transition(state, "GO_B2")
    assert machine.transition(state, "GO").value == {"a": "a2", "b": "b2"}


def test_stateIn_alias_matches_state_id():
    machine = _parallel_machine_with_guard(stateIn("#ready"))
    state = machine.initial_state

    assert machine.transition(state, "GO").value == {"a": "a1", "b": "b1"}

    state = machine.transition(state, "GO_B2")
    assert machine.transition(state, "GO").value == {"a": "a2", "b": "b2"}


def test_state_in_composes_with_other_guards():
    machine = _parallel_machine_with_guard(
        and_(state_in({"b": "b2"}), lambda context, event: True)
    )
    state = machine.initial_state

    state = machine.transition(state, "GO_B2")

    assert machine.transition(state, "GO").value == {"a": "a2", "b": "b2"}

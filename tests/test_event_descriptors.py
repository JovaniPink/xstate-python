"""XState v5 event descriptor selection regressions."""

import pytest

from xstate import Machine


def _transition_value(on, event: str):
    machine = Machine(
        {
            "id": "descriptors",
            "initial": "idle",
            "states": {
                "idle": {"on": on},
                "exact": {},
                "long": {},
                "short": {},
                "fallback": {},
            },
        }
    )
    return machine.transition(machine.initial_state, event).value


def test_catch_all_descriptor_matches_any_event():
    assert _transition_value({"*": "fallback"}, "unknown.event") == "fallback"


def test_exact_descriptor_has_priority_over_earlier_wildcard():
    assert (
        _transition_value(
            {"*": "fallback", "user.*": "short", "user.created": "exact"},
            "user.created",
        )
        == "exact"
    )


def test_exact_guard_failure_falls_back_to_partial_wildcard():
    assert (
        _transition_value(
            {
                "user.created": {"target": "exact", "guard": lambda: False},
                "user.*": "short",
            },
            "user.created",
        )
        == "short"
    )


def test_longest_partial_wildcard_has_priority():
    assert (
        _transition_value(
            {"resource.*": "short", "resource.item.*": "long"},
            "resource.item.created",
        )
        == "long"
    )


def test_longer_partial_guard_failure_falls_back_to_shorter_descriptor():
    assert (
        _transition_value(
            {
                "resource.*": "short",
                "resource.item.*": {"target": "long", "guard": lambda: False},
            },
            "resource.item.created",
        )
        == "short"
    )


def test_document_order_is_preserved_within_one_descriptor():
    assert (
        _transition_value(
            {
                "resource.*": [
                    {"target": "long", "guard": lambda: False},
                    "short",
                    "fallback",
                ]
            },
            "resource.created",
        )
        == "short"
    )


@pytest.mark.parametrize("event", ["resource", "resource.item.created"])
def test_partial_wildcard_matches_base_and_dotted_descendants(event: str):
    assert _transition_value({"resource.*": "short"}, event) == "short"


@pytest.mark.parametrize(
    "descriptor",
    ["resource.*.created", "resource*", "resource.item*", "resource.*created"],
)
def test_invalid_wildcard_forms_do_not_match(descriptor: str):
    assert (
        _transition_value(
            {descriptor: "exact", "*": "fallback"}, "resource.item.created"
        )
        == "fallback"
    )


def test_bare_prefix_descriptor_remains_exact_only():
    assert (
        _transition_value({"error": "exact", "*": "fallback"}, "error.platform.worker")
        == "fallback"
    )


def test_parent_is_checked_only_after_all_local_candidates_fail():
    machine = Machine(
        {
            "id": "parent-fallback",
            "initial": "active",
            "states": {
                "active": {
                    "initial": "child",
                    "states": {
                        "child": {
                            "on": {
                                "task.done": {
                                    "target": "local",
                                    "guard": lambda: False,
                                },
                                "task.*": {
                                    "target": "local",
                                    "guard": lambda: False,
                                },
                            }
                        },
                        "local": {},
                    },
                    "on": {"task.*": "outside"},
                },
                "outside": {},
            },
        }
    )

    state = machine.transition(machine.initial_state, "task.done")

    assert state.value == "outside"


def test_parallel_regions_select_descriptors_independently():
    machine = Machine(
        {
            "id": "parallel-descriptors",
            "type": "parallel",
            "states": {
                "left": {
                    "initial": "waiting",
                    "states": {
                        "waiting": {"on": {"job.*": "done"}},
                        "done": {},
                    },
                },
                "right": {
                    "initial": "waiting",
                    "states": {
                        "waiting": {"on": {"*": "done"}},
                        "done": {},
                    },
                },
            },
        }
    )

    state = machine.transition(machine.initial_state, "job.finished")

    assert state.value == {"left": "done", "right": "done"}

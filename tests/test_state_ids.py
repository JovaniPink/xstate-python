"""Resolved state IDs are unique across the complete machine hierarchy."""

import json

import pytest

from xstate import (
    HandlerArgs,
    InvalidConfigError,
    Machine,
    assign,
    from_callback,
    setup,
)


@pytest.fixture(params=["machine", "strict", "setup"])
def construct_machine(request):
    if request.param == "setup":
        return lambda config, **implementations: setup(
            **implementations
        ).create_machine(config)
    return lambda config, **implementations: Machine(
        config, strict=request.param == "strict", **implementations
    )


@pytest.mark.parametrize(
    ("states", "duplicate_id", "first_path", "second_path"),
    [
        pytest.param(
            {"first": {"id": "shared"}, "second": {"id": "shared"}},
            "shared",
            "states.first",
            "states.second",
            id="explicit-siblings",
        ),
        pytest.param(
            {
                "first": {"id": "shared"},
                "second": {
                    "initial": "child",
                    "states": {"child": {"id": "shared"}},
                },
            },
            "shared",
            "states.first",
            "states.second.states.child",
            id="explicit-across-depths",
        ),
        pytest.param(
            {"first": {}, "second": {"id": "m.first"}},
            "m.first",
            "states.first",
            "states.second",
            id="generated-before-explicit",
        ),
        pytest.param(
            {"first": {"id": "m.second"}, "second": {}},
            "m.second",
            "states.first",
            "states.second",
            id="explicit-before-generated",
        ),
        pytest.param(
            {"first": {"id": "m"}},
            "m",
            "<root>",
            "states.first",
            id="explicit-collides-with-root",
        ),
        pytest.param(
            {
                "first": {
                    "initial": "child",
                    "states": {
                        "child": {"id": "shared"},
                        "hist": {"id": "shared", "type": "history"},
                    },
                }
            },
            "shared",
            "states.first.states.child",
            "states.first.states.hist",
            id="history-collides-with-state",
        ),
        pytest.param(
            {
                "first": {"initial": "child", "states": {"child": {}}},
                "first.child": {},
            },
            "m.first.child",
            "states.first.states.child",
            "states['first.child']",
            id="generated-path-collision",
        ),
        pytest.param(
            {
                "first": {
                    "id": "parent",
                    "initial": "child",
                    "states": {"child": {"id": "shared"}},
                },
                "first.states.child": {"id": "shared"},
            },
            "shared",
            "states.first.states.child",
            "states['first.states.child']",
            id="ambiguous-literal-path-segment",
        ),
    ],
)
def test_duplicate_resolved_ids_report_both_origins(
    construct_machine, states, duplicate_id, first_path, second_path
):
    config = json.loads(json.dumps({"id": "m", "initial": "first", "states": states}))

    with pytest.raises(InvalidConfigError) as exc:
        construct_machine(config)

    assert str(exc.value) == (
        f"Duplicate resolved state id {duplicate_id!r} at {second_path}; "
        f"already used by {first_path}."
    )


def test_duplicate_ids_fail_before_resolving_targets(construct_machine):
    config = {
        "id": "m",
        "initial": "first",
        "states": {
            "first": {"id": "shared", "on": {"GO": "missing"}},
            "second": {"id": "shared"},
        },
    }

    with pytest.raises(
        InvalidConfigError, match="Duplicate resolved state id 'shared'"
    ):
        construct_machine(config)


def test_duplicate_ids_fail_without_running_implementations(construct_machine):
    calls = []

    def callback(_args: HandlerArgs):
        calls.append("handler")
        return {}

    def worker():
        calls.append("actor")

    config = {
        "id": "m",
        "initial": "first",
        "entry": "record",
        "states": {
            "first": {
                "id": "shared",
                "entry": "update",
                "on": {"GO": {"target": "second", "guard": "check"}},
                "after": {"later": "second"},
                "invoke": {"src": "worker", "input": callback},
            },
            "second": {"id": "shared", "type": "final", "output": callback},
        },
    }

    with pytest.raises(
        InvalidConfigError, match="Duplicate resolved state id 'shared'"
    ):
        construct_machine(
            config,
            actions={"record": callback, "update": assign(callback)},
            guards={"check": callback},
            delays={"later": callback},
            actors={"worker": from_callback(worker)},
        )

    assert calls == []


def test_scoped_local_names_keep_distinct_targets_and_history(construct_machine):
    config = {
        "id": "m",
        "initial": "off",
        "states": {
            "off": {
                "on": {
                    "LEFT": "#left-phase.idle",
                    "RIGHT": "#right-phase.idle",
                    "RESTORE_LEFT": "#left-history",
                    "RESTORE_RIGHT": "#right-history",
                }
            },
            **{
                side: {
                    "id": f"{side}-phase",
                    "initial": "idle",
                    "on": {"LEAVE": "#m.off"},
                    "states": {
                        "idle": {"on": {"WORK": "busy"}},
                        "busy": {},
                        "hist": {"id": f"{side}-history", "type": "history"},
                    },
                }
                for side in ("left", "right")
            },
        },
    }
    machine = construct_machine(json.loads(json.dumps(config)))
    state = machine.initial_state
    for event, expected in [
        ("LEFT", {"left": "idle"}),
        ("WORK", {"left": "busy"}),
        ("LEAVE", "off"),
        ("RIGHT", {"right": "idle"}),
        ("LEAVE", "off"),
        ("RESTORE_LEFT", {"left": "busy"}),
        ("LEAVE", "off"),
        ("RESTORE_RIGHT", {"right": "idle"}),
    ]:
        state = machine.transition(state, event)
        assert state.value == expected

    assert machine.root.id == "m"
    for side in ("left", "right"):
        assert machine.states[side].id == f"{side}-phase"
        assert machine.states[side].states["idle"].id == f"{side}-phase.idle"
        assert machine.states[side].states["hist"].id == f"{side}-history"

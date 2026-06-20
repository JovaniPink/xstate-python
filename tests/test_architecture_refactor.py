from __future__ import annotations

from dataclasses import dataclass

import pytest

from xstate import (
    HandlerArgs,
    InvalidConfigError,
    Machine,
    assign,
    dataclass_context,
    interpret,
    raise_,
    setup,
)
from xstate.config_parser import StateNodeConfigParser


def test_parser_resolves_transition_targets_once():
    machine = Machine(
        {
            "id": "resolved",
            "initial": "idle",
            "states": {
                "idle": {"on": {"GO": "done"}},
                "done": {},
            },
        }
    )

    transition = machine.states["idle"].transitions[0]

    assert transition.target == [machine.states["done"]]


def test_parser_accepts_resolved_nodes_inside_target_lists():
    machine = Machine(
        {
            "id": "resolved-list",
            "initial": "idle",
            "states": {
                "idle": {},
                "done": {},
            },
        }
    )
    parser = StateNodeConfigParser(machine)

    targets = parser._resolve_targets(
        machine.states["idle"], [machine.states["done"]], "states.idle.on.GO"
    )

    assert targets == [machine.states["done"]]


def test_schema_models_literal_in_transition_key():
    from xstate.schema import TransitionConfig

    assert "in" in TransitionConfig.__annotations__
    assert "in_" not in TransitionConfig.__annotations__


def test_parser_rejects_invalid_transition_type_with_path():
    with pytest.raises(InvalidConfigError, match=r"states\.idle\.on\.GO\[0\]\.type"):
        Machine(
            {
                "id": "bad-transition-type",
                "initial": "idle",
                "states": {
                    "idle": {
                        "on": {
                            "GO": {
                                "target": "done",
                                "type": "sideways",
                            }
                        }
                    },
                    "done": {},
                },
            }
        )


def test_handler_adapter_accepts_union_handler_args_annotation():
    calls = []
    namespace = {"HandlerArgs": HandlerArgs, "calls": calls}
    exec(
        "def is_allowed(payload: HandlerArgs | None) -> bool:\n"
        "    calls.append((payload.context['allowed'], payload.event.name))\n"
        "    return payload.context['allowed']\n",
        namespace,
    )

    machine = Machine(
        {
            "id": "union-args",
            "context": {"allowed": True},
            "initial": "idle",
            "states": {
                "idle": {
                    "on": {
                        "GO": {
                            "target": "done",
                            "guard": namespace["is_allowed"],
                        }
                    }
                },
                "done": {},
            },
        }
    )

    state = machine.transition(machine.initial_state, "GO")

    assert state.value == "done"
    assert calls == [(True, "GO")]


def test_setup_canonical_handler_args_guard_assign_and_action_params():
    log = []

    def is_over(args: HandlerArgs) -> bool:
        return args.context["count"] > args.params["min"]

    def record(args: HandlerArgs) -> None:
        log.append((args.params["label"], args.event.name, args.context["count"]))

    machine = setup(
        guards={"isOver": is_over},
        actions={"record": record},
    ).create_machine(
        {
            "id": "strict",
            "context": {"count": 2},
            "initial": "idle",
            "states": {
                "idle": {
                    "on": {
                        "GO": {
                            "target": "done",
                            "guard": {"type": "isOver", "params": {"min": 1}},
                            "actions": [
                                assign(
                                    {"count": lambda args: args.context["count"] + 1}
                                ),
                                {"type": "record", "params": {"label": "passed"}},
                            ],
                        }
                    }
                },
                "done": {},
            },
        }
    )

    service = interpret(machine).start()
    service.send("GO")

    assert service.state.value == "done"
    assert service.state.context["count"] == 3
    assert log == [("passed", "GO", 3)]


def test_setup_warns_for_legacy_handler_signatures():
    with pytest.warns(DeprecationWarning, match="legacy callable signature"):
        setup(guards={"ok": lambda ctx, event: True}).create_machine(
            {
                "id": "legacy",
                "initial": "idle",
                "states": {
                    "idle": {"on": {"GO": {"target": "done", "guard": "ok"}}},
                    "done": {},
                },
            }
        )


def test_parser_reports_invoke_src_path():
    with pytest.raises(InvalidConfigError, match=r"states\.run\.invoke\[0\]\.src"):
        Machine(
            {
                "id": "bad",
                "initial": "run",
                "states": {"run": {"invoke": {}}},
            }
        )


def test_parser_preserves_none_key_as_eventless_transition():
    machine = Machine(
        {
            "id": "none-eventless",
            "initial": "a",
            "states": {
                "a": {"on": {"t": "b"}},
                "b": {
                    "entry": [raise_("s")],
                    "on": {None: "f1", "s": "c"},
                },
                "c": {},
                "f1": {},
            },
        }
    )

    state = machine.transition(machine.initial_state, "t")

    assert state.value == "f1"


@dataclass(frozen=True)
class CounterContext:
    count: int = 0


def test_dataclass_context_adapter_preserves_immutable_snapshots():
    machine = Machine(
        {
            "id": "dataclass",
            "context": CounterContext(),
            "initial": "active",
            "states": {
                "active": {
                    "on": {
                        "INC": {
                            "actions": [
                                assign({"count": lambda args: args.context.count + 1})
                            ]
                        }
                    }
                }
            },
        },
        context_adapter=dataclass_context(),
    )

    s0 = machine.initial_state
    s1 = machine.transition(s0, "INC")
    s2 = machine.transition(s1, "INC")

    assert s0.context == CounterContext(count=0)
    assert s1.context == CounterContext(count=1)
    assert s2.context == CounterContext(count=2)

from __future__ import annotations

from typing import Any, assert_type

from xstate import Event, Machine, State, interpret


def legacy_action(context: dict[str, Any], event: Event) -> None:
    context["seen"] = event.name


def legacy_guard(context: dict[str, Any], event: Event) -> bool:
    return bool(context) and event.name == "GO"


machine: Machine = Machine(
    {
        "id": "legacy",
        "context": {"seen": None},
        "initial": "idle",
        "states": {
            "idle": {
                "on": {
                    "GO": {
                        "target": "done",
                        "guard": "allowed",
                        "actions": "record",
                    }
                }
            },
            "done": {},
        },
    },
    actions={"record": legacy_action},
    guards={"allowed": legacy_guard},
)
assert_type(machine, Machine[Any, Any, Any])
assert_type(machine.transition(machine.initial_state, "GO"), State[Any, Any, Any])
assert_type(interpret(machine).send({"type": "GO"}), State[Any, Any, Any])

from collections.abc import Callable

import pytest

from xstate import HandlerArgs, Machine, interpret


def recorder(log: list[str], label: str) -> Callable[[HandlerArgs], None]:
    def record(_args: HandlerArgs) -> None:
        log.append(label)

    return record


def test_nested_actions_follow_exit_transition_entry_order() -> None:
    log: list[str] = []
    labels = (
        "left.enter",
        "child.enter",
        "child.exit",
        "left.exit",
        "transition",
        "right.enter",
    )
    machine = Machine(
        {
            "id": "nested-order",
            "initial": "left",
            "states": {
                "left": {
                    "entry": "left.enter",
                    "exit": "left.exit",
                    "initial": "child",
                    "states": {
                        "child": {
                            "entry": "child.enter",
                            "exit": "child.exit",
                            "on": {
                                "GO": {
                                    "target": "#right",
                                    "actions": "transition",
                                }
                            },
                        }
                    },
                },
                "right": {"id": "right", "entry": "right.enter"},
            },
        },
        actions={label: recorder(log, label) for label in labels},
    )
    service = interpret(machine).start()

    assert log == ["left.enter", "child.enter"]

    log.clear()
    service.send("GO")

    assert log == [
        "child.exit",
        "left.exit",
        "transition",
        "right.enter",
    ]


@pytest.mark.parametrize(
    "region_order",
    [("alpha", "beta"), ("beta", "alpha")],
)
def test_parallel_entries_follow_region_document_order(
    region_order: tuple[str, str],
) -> None:
    log: list[str] = []
    actions = {"active.enter": recorder(log, "active.enter")}
    regions = {}
    for region in region_order:
        actions[f"{region}.enter"] = recorder(log, f"{region}.enter")
        actions[f"{region}.idle.enter"] = recorder(log, f"{region}.idle.enter")
        regions[region] = {
            "entry": f"{region}.enter",
            "initial": "idle",
            "states": {"idle": {"entry": f"{region}.idle.enter"}},
        }

    machine = Machine(
        {
            "id": "parallel-entry-order",
            "initial": "active",
            "states": {
                "active": {
                    "type": "parallel",
                    "entry": "active.enter",
                    "states": regions,
                }
            },
        },
        actions=actions,
    )

    interpret(machine).start()

    assert log == [
        "active.enter",
        f"{region_order[0]}.enter",
        f"{region_order[0]}.idle.enter",
        f"{region_order[1]}.enter",
        f"{region_order[1]}.idle.enter",
    ]


@pytest.mark.parametrize(
    "region_order",
    [("alpha", "beta"), ("beta", "alpha")],
)
def test_parallel_exits_follow_reverse_region_document_order(
    region_order: tuple[str, str],
) -> None:
    log: list[str] = []
    labels = ["active.exit", "transition", "done.enter"]
    regions = {}
    for region in region_order:
        labels.extend((f"{region}.exit", f"{region}.idle.exit"))
        regions[region] = {
            "exit": f"{region}.exit",
            "initial": "idle",
            "states": {"idle": {"exit": f"{region}.idle.exit"}},
        }

    machine = Machine(
        {
            "id": "parallel-exit-order",
            "initial": "active",
            "states": {
                "active": {
                    "type": "parallel",
                    "exit": "active.exit",
                    "on": {
                        "STOP": {
                            "target": "#done",
                            "actions": "transition",
                        }
                    },
                    "states": regions,
                },
                "done": {"id": "done", "entry": "done.enter"},
            },
        },
        actions={label: recorder(log, label) for label in labels},
    )
    service = interpret(machine).start()

    log.clear()
    service.send("STOP")

    assert log == [
        f"{region_order[1]}.idle.exit",
        f"{region_order[1]}.exit",
        f"{region_order[0]}.idle.exit",
        f"{region_order[0]}.exit",
        "active.exit",
        "transition",
        "done.enter",
    ]

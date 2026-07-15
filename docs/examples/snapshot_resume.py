#!/usr/bin/env python3
"""Checkpoint a machine actor to JSON and resume it on a new actor."""

import json

from xstate import (
    Machine,
    assign,
    create_actor,
    deserialize_snapshot,
    serialize_snapshot,
)


def build_machine() -> Machine:
    return Machine(
        {
            "id": "durable-counter",
            "context": {"count": 0},
            "initial": "active",
            "states": {
                "active": {
                    "on": {
                        "INCREMENT": {
                            "actions": assign(
                                {"count": lambda context, _event: context["count"] + 1}
                            )
                        }
                    }
                }
            },
        }
    )


def main() -> None:
    machine = build_machine()
    original = create_actor(machine).start()
    original.send("INCREMENT")
    original.send("INCREMENT")

    payload = json.dumps(serialize_snapshot(original.get_snapshot()))
    original.stop()

    restored = deserialize_snapshot(machine, json.loads(payload))
    resumed = create_actor(machine, snapshot=restored).start()

    assert resumed.get_snapshot().value == "active"
    assert resumed.get_snapshot().context == {"count": 2}

    resumed.send("INCREMENT")
    assert resumed.get_snapshot().context == {"count": 3}

    resumed.stop()
    print("resumed durable counter at 3")


if __name__ == "__main__":
    main()

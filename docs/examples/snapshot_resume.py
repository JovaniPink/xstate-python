#!/usr/bin/env python3
"""Round-trip active and completed snapshots through JSON, without disk storage."""

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
            "id": "checkpoint-counter",
            "context": {"count": 0},
            "initial": "active",
            "states": {
                "active": {
                    "on": {
                        "INCREMENT": {
                            "actions": assign(
                                {"count": lambda context, _event: context["count"] + 1}
                            )
                        },
                        "FINISH": "done",
                    }
                },
                "done": {
                    "type": "final",
                    "output": lambda context, _event: {"total": context["count"]},
                },
            },
        }
    )


def main() -> None:
    machine = build_machine()
    original = create_actor(machine)
    try:
        original.start()
        original.send("INCREMENT")
        original.send("INCREMENT")
        payload = json.dumps(serialize_snapshot(original.get_snapshot()))
    finally:
        # Stop the previous owner before resuming, even if serialization fails.
        original.stop()

    restored = deserialize_snapshot(machine, json.loads(payload))
    resumed = create_actor(machine, snapshot=restored)
    try:
        assert resumed.get_snapshot() is restored
        assert resumed.status == "not_started"
        assert restored.matches("active")
        assert restored.context == {"count": 2}
        print("before start: active; count=2")
        resumed.start()
        resumed.send("INCREMENT")
        assert resumed.get_snapshot().context == {"count": 3}
        print("after resume: active; count=3")

        resumed.send("FINISH")
        completed_payload = json.dumps(serialize_snapshot(resumed.get_snapshot()))
    finally:
        resumed.stop()

    # A completed output is stored data; deserialization does not call the
    # output function again. This is still an in-memory JSON round-trip.
    completed = deserialize_snapshot(machine, json.loads(completed_payload))
    assert completed.status == "done"
    assert completed.output == {"total": 3}
    print(f"restored completed output: {completed.output}")


if __name__ == "__main__":
    main()

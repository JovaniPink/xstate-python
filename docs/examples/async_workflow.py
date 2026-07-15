#!/usr/bin/env python3
"""Run a machine with an awaitable action through AsyncInterpreter."""

import asyncio

from xstate import HandlerArgs, Machine, interpret_async


async def main() -> None:
    completed_jobs: list[int] = []

    async def record_job(args: HandlerArgs) -> None:
        await asyncio.sleep(0)
        completed_jobs.append(args.event.data["job_id"])

    machine = Machine(
        {
            "id": "async-workflow",
            "initial": "idle",
            "states": {
                "idle": {
                    "on": {
                        "RUN": {
                            "target": "done",
                            "actions": "recordJob",
                        }
                    }
                },
                "done": {"type": "final"},
            },
        },
        actions={"recordJob": record_job},
    )

    observed: list[object] = []
    service = interpret_async(machine)
    await service.start()
    subscription = service.subscribe(lambda snapshot: observed.append(snapshot.value))

    snapshot = await service.send({"type": "RUN", "job_id": 42})

    assert snapshot.value == "done"
    assert snapshot.status == "done"
    assert completed_jobs == [42]
    assert observed == ["idle", "done"]

    subscription.unsubscribe()
    await service.stop()
    print("completed async job 42")


if __name__ == "__main__":
    asyncio.run(main())

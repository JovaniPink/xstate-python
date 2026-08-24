# Static typing

The public API is generic without adding runtime schemas or validation. Existing
unparameterized `Machine(...)` calls remain `Any`-compatible. Add type arguments
when a consumer wants mypy to check context, event objects, output, snapshots,
and runtime sends end to end.

`EventDataT` is the complete external event mapping, including its required
`type` discriminator. This matches [XState event objects](https://stately.ai/docs/transitions),
not a payload nested below `type`.

## Machine and handlers

```python
from typing import Literal, TypedDict, assert_type

from xstate import HandlerArgs, Machine, MachineConfig, State


class Context(TypedDict):
    count: int


class AddEvent(TypedDict):
    type: Literal["ADD"]
    by: int


class FinishEvent(TypedDict):
    type: Literal["FINISH"]


type CounterEvent = AddEvent | FinishEvent


class Output(TypedDict):
    total: int


def final_output(
    args: HandlerArgs[Context, CounterEvent, Output],
) -> Output:
    return {"total": args.context["count"]}


config: MachineConfig[Context, CounterEvent, Output] = {
    "id": "counter",
    "context": {"count": 0},
    "initial": "active",
    "states": {
        "active": {"on": {"FINISH": "done"}},
        "done": {"type": "final", "output": final_output},
    },
}

machine: Machine[Context, CounterEvent, Output] = Machine(config)
snapshot = machine.transition(machine.initial_state, {"type": "FINISH"})

assert_type(snapshot, State[Context, CounterEvent, Output])
assert_type(snapshot.context, Context)
assert_type(snapshot.output, Output | None)
```

`HandlerArgs.event` also represents runtime-generated done and error events, so
its data is typed as the union of external event data, machine or actor output,
and `BaseException`. Narrow by event name or data shape before reading fields.

Canonical handler protocols are exported as `ActionHandler`, `GuardHandler`,
`DelayHandler`, `AssignmentHandler`, and `OutputHandler`. Annotating a handler
with one of these protocols makes an incorrect return type fail at type-check
time. Legacy zero-, one-, two-, and keyword-argument callables remain accepted
at runtime.

## Setup and interpreters

```python
from typing import Any, assert_type

from xstate import AsyncInterpreter, Interpreter, MachineSetup, interpret, interpret_async, setup

configured: MachineSetup[Context, CounterEvent, Output] = setup()
machine = configured.create_machine(config)

service = interpret(machine)
assert_type(service, Interpreter[Context, CounterEvent, Output])
assert_type(
    service.send({"type": "ADD", "by": 2}),
    State[Context, CounterEvent, Output],
)

async_service = interpret_async(machine)
assert_type(async_service, AsyncInterpreter[Context, CounterEvent, Output])


async def finish() -> None:
    result = await async_service.send({"type": "FINISH"})
    assert_type(result, State[Context, CounterEvent, Output])
```

Subscriptions receive the same typed `State`, so a listener can be declared as
`Callable[[State[Context, CounterEvent, Output]], None]` without casts.

## Actors

```python
import asyncio
from typing import Any, assert_type

from xstate import (
    Actor,
    ActorRef,
    ActorSnapshot,
    EventInput,
    create_actor,
    from_promise,
    to_promise,
)

machine_actor = create_actor(machine)
assert_type(
    machine_actor,
    Actor[
        EventInput[CounterEvent],
        State[Context, CounterEvent, Output],
        Output,
    ],
)


def calculate(input: int) -> Output:
    return {"total": input}


promise_actor = create_actor(from_promise(calculate), input=3)
assert_type(promise_actor, Actor[object, ActorSnapshot[Output], Output])
assert_type(to_promise(promise_actor), asyncio.Future[Output])
assert_type(machine_actor.system.get("child"), ActorRef[Any, Any] | None)
```

Known machine, promise, callback, and observable logic preserves precise actor
types. Consumer-only boundaries can accept `ActorRef[SendEventT, SnapshotT]`
without acquiring lifecycle control. `ActorSystem.get()` is intentionally
widened because one system may hold heterogeneous actors.

Raw JSON dictionaries, string events, and unparameterized machines remain valid.
These annotations guide static consumers only; they do not generate code or add
a runtime validation dependency.

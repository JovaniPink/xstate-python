from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, Callable
from typing import Any, Literal, TypedDict, assert_type

from xstate import (
    ActionHandler,
    Actor,
    ActorRef,
    ActorSnapshot,
    AssignmentHandler,
    AsyncInterpreter,
    CompletionSnapshot,
    ContextAdapter,
    DeepCopyContextAdapter,
    DelayHandler,
    Event,
    EventInput,
    GuardHandler,
    HandlerArgs,
    Interpreter,
    Machine,
    MachineConfig,
    MachineOptionsConfig,
    MachineSetup,
    MachineSnapshot,
    MacrostepTrace,
    MicrostepTrace,
    OutputHandler,
    State,
    SubscriptionProtocol,
    TransitionTrace,
    create_actor,
    from_callback,
    from_observable,
    from_promise,
    get_initial_microsteps,
    get_microsteps,
    interpret,
    interpret_async,
    setup,
    to_promise,
)


class Context(TypedDict):
    count: int


class IncrementEvent(TypedDict):
    type: Literal["INCREMENT"]
    by: int


class FinishEvent(TypedDict):
    type: Literal["FINISH"]


type AppEvent = IncrementEvent | FinishEvent


class Output(TypedDict):
    total: int


def can_increment(args: HandlerArgs[Context, AppEvent, Output]) -> bool:
    return args.context["count"] < 10


def final_output(args: HandlerArgs[Context, AppEvent, Output]) -> Output:
    return {"total": args.context["count"]}


def record(args: HandlerArgs[Context, AppEvent, Output]) -> None:
    _ = args
    return None


def update(args: HandlerArgs[Context, AppEvent, Output]) -> dict[str, object]:
    _ = args
    return {"count": 1}


def short_delay(args: HandlerArgs[Context, AppEvent, Output]) -> float:
    _ = args
    return 10.0


guard: GuardHandler[Context, AppEvent, Output] = can_increment
output_handler: OutputHandler[Context, AppEvent, Output] = final_output
action: ActionHandler[Context, AppEvent, Output] = record
assignment: AssignmentHandler[Context, AppEvent, Output] = update
delay: DelayHandler[Context, AppEvent, Output] = short_delay
context_adapter: ContextAdapter[Context] = DeepCopyContextAdapter()
assert_type(context_adapter.snapshot({"count": 0}), Context)

config: MachineConfig[Context, AppEvent, Output] = {
    "id": "counter",
    "context": {"count": 0},
    "initial": "active",
    "states": {
        "active": {
            "on": {
                "INCREMENT": {"target": "active", "guard": guard},
                "FINISH": "done",
            }
        },
        "done": {"type": "final", "output": output_handler},
    },
}
options: MachineOptionsConfig = {"maxIterations": 10}
config["options"] = options

machine: Machine[Context, AppEvent, Output] = Machine(config, max_iterations=20)
state = machine.initial_state
assert_type(state, State[Context, AppEvent, Output])
assert_type(state, MachineSnapshot[Context, AppEvent, Output])
state = machine.transition(state, {"type": "INCREMENT", "by": 2})
assert_type(state.context, Context)
assert_type(state.output, Output | None)
assert_type(state.event, Event[AppEvent | Output | BaseException] | None)
finish_event: FinishEvent = {"type": "FINISH"}
assert_type(
    get_microsteps(machine, state, finish_event),
    tuple[MicrostepTrace[Context, AppEvent, Output], ...],
)
assert_type(
    get_initial_microsteps(machine),
    tuple[MicrostepTrace[Context, AppEvent, Output], ...],
)
transition_trace = TransitionTrace("FINISH", "counter.active", ("counter.done",))
assert_type(transition_trace.target_ids, tuple[str, ...])


def inspect_trace(trace: MacrostepTrace[Context, AppEvent, Output]) -> None:
    assert_type(trace.snapshot, State[Context, AppEvent, Output])
    assert_type(trace.microsteps, tuple[MicrostepTrace[Context, AppEvent, Output], ...])


service = interpret(machine, inspect=inspect_trace)
assert_type(service, Interpreter[Context, AppEvent, Output])
assert_type(
    service.send({"type": "INCREMENT", "by": 1}),
    State[Context, AppEvent, Output],
)


def observe(snapshot: State[Context, AppEvent, Output]) -> None:
    assert_type(snapshot.context, Context)


service.subscribe(observe)

async_service = interpret_async(machine, inspect=inspect_trace)
assert_type(async_service, AsyncInterpreter[Context, AppEvent, Output])


async def use_async() -> None:
    assert_type(
        await async_service.send({"type": "FINISH"}),
        State[Context, AppEvent, Output],
    )


machine_actor = create_actor(machine, inspect=inspect_trace)
assert_type(
    machine_actor,
    Actor[EventInput[AppEvent], State[Context, AppEvent, Output], Output],
)
assert_type(machine_actor.get_snapshot(), State[Context, AppEvent, Output])
machine_actor.subscribe(observe)
assert_type(machine_actor.parent, ActorRef[Any, Any] | None)
assert_type(machine_actor.children, dict[str, ActorRef[Any, Any]])
assert_type(machine_actor.system.get("child"), ActorRef[Any, Any] | None)
machine_ref: ActorRef[EventInput[AppEvent], State[Context, AppEvent, Output]] = (
    machine_actor
)


def promise(input: int) -> Output:
    return {"total": input}


promise_actor = create_actor(from_promise(promise), input=2)
assert_type(promise_actor, Actor[object, ActorSnapshot[Output], Output])
assert_type(to_promise(promise_actor), asyncio.Future[Output])
promise_ref: ActorRef[object, ActorSnapshot[Output]] = promise_actor
assert_type(to_promise(promise_ref), asyncio.Future[Output])
spawned_promise = machine_actor.spawn(from_promise(promise), input=3)
assert_type(spawned_promise, Actor[object, ActorSnapshot[Output], Output])


class RefSubscription:
    def unsubscribe(self) -> None:
        return None


class StructuralRef:
    id = "structural"

    def __init__(self) -> None:
        self.snapshot: CompletionSnapshot[Output] = ActorSnapshot[Output](
            "done", output={"total": 2}
        )

    def send(self, event: object) -> CompletionSnapshot[Output]:
        _ = event
        return self.snapshot

    def get_snapshot(self) -> CompletionSnapshot[Output]:
        return self.snapshot

    def subscribe(
        self,
        listener: Callable[[CompletionSnapshot[Output]], None],
    ) -> SubscriptionProtocol:
        listener(self.snapshot)
        return RefSubscription()


structural_ref: ActorRef[object, CompletionSnapshot[Output]] = StructuralRef()
assert_type(to_promise(structural_ref), asyncio.Future[Output])


async def values(input: int) -> AsyncIterable[int]:
    yield input


observable_actor = create_actor(from_observable(values), input=1)
assert_type(observable_actor, Actor[object, ActorSnapshot[int], int])


class CallbackEvent(TypedDict):
    type: Literal["PING"]


def callback(
    *,
    send_back: Callable[[object], None],
    receive: Callable[[Callable[[CallbackEvent], None]], None],
    input: int,
) -> None:
    receive(lambda event: send_back((input, event)))


callback_actor = create_actor(from_callback(callback), input=1)
assert_type(
    callback_actor,
    Actor[CallbackEvent, ActorSnapshot[None], None],
)
callback_actor.send({"type": "PING"})

machine_setup: MachineSetup[Context, AppEvent, Output] = setup(guards={"ok": guard})
assert_type(machine_setup.create_machine(config), Machine[Context, AppEvent, Output])

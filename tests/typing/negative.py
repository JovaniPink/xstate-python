from __future__ import annotations

from typing import Literal, TypedDict

from xstate import (
    ActorRef,
    ActorSnapshot,
    Event,
    GuardHandler,
    HandlerArgs,
    Machine,
    MachineOptionsConfig,
    MacrostepTrace,
    OutputHandler,
    State,
    create_actor,
    interpret,
)


class Context(TypedDict):
    count: int


class IncrementEvent(TypedDict):
    type: Literal["INCREMENT"]
    by: int


class Output(TypedDict):
    total: int


machine: Machine[Context, IncrementEvent, Output] = Machine(
    {
        "id": "counter",
        "context": {"count": 0},
        "initial": "active",
        "states": {"active": {}},
    }
)
state = machine.initial_state

machine.transition(state, {"type": "INCREMENT"})  # invalid-event-payload
interpret(machine).send({"type": "OTHER", "by": 1})  # invalid-send

bad_context: str = state.context  # invalid-snapshot-context
bad_output: str = state.output  # invalid-snapshot-output


def wrong_guard(_args: HandlerArgs[Context, IncrementEvent, Output]) -> str:
    return "yes"


def wrong_output(_args: HandlerArgs[Context, IncrementEvent, Output]) -> str:
    return "wrong"


guard: GuardHandler[Context, IncrementEvent, Output] = wrong_guard  # invalid-guard
output: OutputHandler[Context, IncrementEvent, Output] = (  # invalid-output-handler
    wrong_output
)
event = Event[IncrementEvent]("INCREMENT", {"type": "INCREMENT"})  # invalid-event
options: MachineOptionsConfig = {"maxIterations": "2"}  # invalid-options
Machine({"id": "bad", "states": {}}, max_iterations="2")  # invalid-limit


def wrong_inspector(_trace: State[Context, IncrementEvent, Output]) -> None:
    return None


interpret(machine, inspect=wrong_inspector)  # invalid-inspector


def valid_inspector(
    trace: MacrostepTrace[Context, IncrementEvent, Output],
) -> None:
    bad_snapshot: State[str, IncrementEvent, Output] = trace.snapshot  # invalid-trace
    _ = bad_snapshot


actor_ref: ActorRef[IncrementEvent, State[Context, IncrementEvent, Output]] = (
    create_actor(machine)
)
actor_ref.send({"type": "OTHER", "by": 1})  # invalid-actor-ref-send
wrong_ref_snapshot: ActorSnapshot[Output] = (  # invalid-actor-ref-snapshot
    actor_ref.get_snapshot()
)

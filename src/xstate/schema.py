from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, TypedDict

from xstate.handlers import ActionHandler, GuardHandler, OutputHandler

StateNodeType = Literal["atomic", "compound", "parallel", "final", "history"]

type LegacyHandler = Callable[..., Any]
type HandlerSpec[ContextT = Any, EventDataT = Any, OutputT = Any] = (
    str | dict[str, Any] | GuardHandler[ContextT, EventDataT, OutputT] | LegacyHandler
)
type ActionSpec[ContextT = Any, EventDataT = Any, OutputT = Any] = (
    str | dict[str, Any] | ActionHandler[ContextT, EventDataT, OutputT] | LegacyHandler
)
type TransitionTarget = str | list[str]
type StateValue = str | dict[str, StateValue]

__all__ = [
    "StateNodeType",
    "HandlerSpec",
    "ActionSpec",
    "TransitionTarget",
    "StateValue",
    "TransitionConfig",
    "InvokeConfig",
    "StateNodeConfig",
    "MachineConfig",
]


_TransitionInConfig = TypedDict(
    "_TransitionInConfig",
    {"in": Any},
    total=False,
)


class TransitionConfig[ContextT = Any, EventDataT = Any, OutputT = Any](
    _TransitionInConfig, total=False
):
    target: TransitionTarget
    actions: (
        ActionSpec[ContextT, EventDataT, OutputT]
        | list[ActionSpec[ContextT, EventDataT, OutputT]]
    )
    guard: HandlerSpec[ContextT, EventDataT, OutputT]
    cond: HandlerSpec[ContextT, EventDataT, OutputT]
    type: Literal["internal", "external"]


class InvokeConfig[ContextT = Any, EventDataT = Any, OutputT = Any](
    TypedDict, total=False
):
    id: str
    src: Any
    input: Any
    onDone: (
        TransitionConfig[ContextT, EventDataT, OutputT]
        | str
        | list[TransitionConfig[ContextT, EventDataT, OutputT] | str]
    )
    onError: (
        TransitionConfig[ContextT, EventDataT, OutputT]
        | str
        | list[TransitionConfig[ContextT, EventDataT, OutputT] | str]
    )
    onSnapshot: (
        TransitionConfig[ContextT, EventDataT, OutputT]
        | str
        | list[TransitionConfig[ContextT, EventDataT, OutputT] | str]
    )
    systemId: str


class StateNodeConfig[ContextT = Any, EventDataT = Any, OutputT = Any](
    TypedDict, total=False
):
    id: str
    type: StateNodeType
    tags: str | list[str]
    meta: Any
    initial: str
    states: dict[str, StateNodeConfig[ContextT, EventDataT, OutputT]]
    on: dict[
        str | None,
        TransitionConfig[ContextT, EventDataT, OutputT]
        | str
        | list[TransitionConfig[ContextT, EventDataT, OutputT] | str],
    ]
    always: (
        TransitionConfig[ContextT, EventDataT, OutputT]
        | str
        | list[TransitionConfig[ContextT, EventDataT, OutputT] | str]
    )
    entry: (
        ActionSpec[ContextT, EventDataT, OutputT]
        | list[ActionSpec[ContextT, EventDataT, OutputT]]
    )
    exit: (
        ActionSpec[ContextT, EventDataT, OutputT]
        | list[ActionSpec[ContextT, EventDataT, OutputT]]
    )
    after: dict[
        Any,
        TransitionConfig[ContextT, EventDataT, OutputT]
        | str
        | list[TransitionConfig[ContextT, EventDataT, OutputT] | str],
    ]
    invoke: (
        InvokeConfig[ContextT, EventDataT, OutputT]
        | list[InvokeConfig[ContextT, EventDataT, OutputT]]
    )
    onDone: (
        TransitionConfig[ContextT, EventDataT, OutputT]
        | str
        | list[TransitionConfig[ContextT, EventDataT, OutputT] | str]
    )
    history: Literal["shallow", "deep"]
    target: TransitionTarget
    output: OutputT | OutputHandler[ContextT, EventDataT, OutputT] | LegacyHandler
    data: Any


class MachineConfig[ContextT = Any, EventDataT = Any, OutputT = Any](
    StateNodeConfig[ContextT, EventDataT, OutputT], total=False
):
    context: ContextT

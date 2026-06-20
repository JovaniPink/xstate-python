from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, TypeAlias, TypedDict

StateNodeType: TypeAlias = Literal["atomic", "compound", "parallel", "final", "history"]

HandlerSpec: TypeAlias = str | dict[str, Any] | Callable[..., Any]
ActionSpec: TypeAlias = str | dict[str, Any] | Callable[..., Any]
TransitionTarget: TypeAlias = str | list[str]


class TransitionConfig(TypedDict, total=False):
    target: TransitionTarget
    actions: ActionSpec | list[ActionSpec]
    guard: HandlerSpec
    cond: HandlerSpec
    in_: Any
    type: Literal["internal", "external"]


class InvokeConfig(TypedDict, total=False):
    id: str
    src: Any
    input: Any
    onDone: TransitionConfig | str | list[TransitionConfig | str]
    onError: TransitionConfig | str | list[TransitionConfig | str]
    onSnapshot: TransitionConfig | str | list[TransitionConfig | str]
    systemId: str


class StateNodeConfig(TypedDict, total=False):
    id: str
    type: StateNodeType
    initial: str
    states: dict[str, StateNodeConfig]
    on: dict[str, TransitionConfig | str | list[TransitionConfig | str]]
    always: TransitionConfig | str | list[TransitionConfig | str]
    entry: ActionSpec | list[ActionSpec]
    exit: ActionSpec | list[ActionSpec]
    after: dict[Any, TransitionConfig | str | list[TransitionConfig | str]]
    invoke: InvokeConfig | list[InvokeConfig]
    onDone: TransitionConfig | str | list[TransitionConfig | str]
    history: Literal["shallow", "deep"]
    target: TransitionTarget
    output: Any
    data: Any


class MachineConfig(StateNodeConfig, total=False):
    context: Any

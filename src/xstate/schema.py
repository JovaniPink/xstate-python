from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, TypedDict, Union

StateNodeType = Literal["atomic", "compound", "parallel", "final", "history"]

HandlerSpec = Union[str, "dict[str, Any]", "Callable[..., Any]"]
ActionSpec = Union[str, "dict[str, Any]", "Callable[..., Any]"]
TransitionTarget = Union[str, "list[str]"]

__all__ = [
    "StateNodeType",
    "HandlerSpec",
    "ActionSpec",
    "TransitionTarget",
    "TransitionConfig",
    "InvokeConfig",
    "StateNodeConfig",
    "MachineConfig",
]


TransitionConfig = TypedDict(
    "TransitionConfig",
    {
        "target": TransitionTarget,
        "actions": ActionSpec | list[ActionSpec],
        "guard": HandlerSpec,
        "cond": HandlerSpec,
        "in": Any,
        "type": Literal["internal", "external"],
    },
    total=False,
)


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
    on: dict[str | None, TransitionConfig | str | list[TransitionConfig | str]]
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

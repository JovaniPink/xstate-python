from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from xstate.action import Action
from xstate.handlers import GuardReference, HandlerAdapter

if TYPE_CHECKING:
    from xstate.state_node import StateNode


__all__ = ["GuardSpec", "Transition"]

type GuardSpec = HandlerAdapter | GuardReference | Callable[..., object] | str


@dataclass(eq=False, slots=True, kw_only=True)
class Transition:
    event: str | None
    source: StateNode
    config: Any
    order: int
    target_nodes: list[StateNode] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    cond: GuardSpec | None = None
    in_state: Any | None = None
    type: Literal["internal", "external"] = "external"

    @property
    def target(self) -> list[StateNode]:
        return self.target_nodes

    def __repr__(self) -> str:
        return (
            f"Transition(event={self.event!r}, source={self.source.id!r},"
            f" target={[f'#{t.id}' for t in self.target]!r})"
        )

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from xstate.action import Action
from xstate.exceptions import InvalidConfigError
from xstate.transition import Transition

if TYPE_CHECKING:
    from xstate.machine import Machine


StateNodeType = Literal["atomic", "compound", "parallel", "final", "history"]

__all__ = ["StateNodeType", "StateNode"]


@dataclass(eq=False, slots=True, kw_only=True)
class StateNode:
    config: dict[str, Any]
    machine: Machine
    key: str
    parent: StateNode | None
    order: int
    id: str
    type: StateNodeType
    states: dict[str, StateNode] = field(default_factory=dict)
    on: dict[str, list[Transition]] = field(default_factory=dict)
    transitions: list[Transition] = field(default_factory=list)
    entry: list[Action] = field(default_factory=list)
    exit: list[Action] = field(default_factory=list)
    donedata: Any | None = None
    history: Literal["shallow", "deep"] | None = None
    transition: Transition | None = None
    after: list[tuple[Any, str]] = field(default_factory=list)
    invoke: list[dict[str, Any]] = field(default_factory=list)
    initial_transition: Transition | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def history_states(self) -> list[StateNode]:
        """Child states of this node that are history pseudo-states."""
        return [s for s in self.states.values() if s.type == "history"]

    @property
    def initial(self) -> Transition:
        if self.initial_transition is None:
            raise InvalidConfigError(
                f"State '#{self.id}' of type '{self.type}' has no initial state."
            )
        return self.initial_transition

    def _get_relative(self, target: str) -> StateNode:
        if target.startswith("#"):
            node = self.machine._get_by_id(target[1:])
            if node is None:
                raise InvalidConfigError(
                    f"No state with id '{target[1:]}' in machine '{self.machine.id}'"
                )
            return node

        if self.parent is None:
            state_node = self.states.get(target)
            if state_node is not None:
                return state_node
            raise InvalidConfigError(
                f"Cannot resolve relative target '{target}' from root state "
                f"node '#{self.id}'"
            )

        state_node = self.parent.states.get(target)
        if state_node is None:
            raise InvalidConfigError(
                f"Relative state node '{target}' does not exist on state "
                f"node '#{self.id}'"
            )
        return state_node

    def __repr__(self) -> str:
        return f"<StateNode {{'id': {self.id!r}}}>"

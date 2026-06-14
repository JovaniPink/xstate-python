from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, List, NamedTuple, Optional, Union

from xstate.action import Action
from xstate.event import Event

if TYPE_CHECKING:
    from xstate.state_node import StateNode

CondFunction = Callable[[Any, Event], bool]


class TransitionConfig(NamedTuple):
    target: List[str]


class Transition:
    event: Optional[str]
    source: StateNode
    config: Union[str, StateNode]
    actions: List[Action]
    cond: Optional[CondFunction]
    order: int
    # "internal" or "external"
    type: str

    def __init__(
        self,
        config,
        source: StateNode,
        event: Optional[str],
        order: int,
        cond: Optional[CondFunction] = None,
    ):
        self.event = event
        self.config = config
        self.source = source
        self.type = "external"
        self.cond = config.get("cond", None) if isinstance(config, dict) else None
        self.in_state = config.get("in", None) if isinstance(config, dict) else None
        self.order = order

        self.actions = (
            (
                [
                    Action(type=action.get("type"), data=action)
                    for action in config.get("actions", [])
                ]
            )
            if isinstance(config, dict)
            else []
        )

    @property
    def target(self) -> List[StateNode]:
        if isinstance(self.config, str):
            return [self.source._get_relative(self.config)]
        elif isinstance(self.config, dict):
            # A dict transition may omit "target" entirely — e.g. a guarded
            # internal self-loop like {"cond": fn} or {"actions": [...]}. Treat
            # the absence of a target as "no state change" rather than crashing.
            target = self.config.get("target")
            if target is None:
                return []
            if isinstance(target, str):
                return [self.source._get_relative(target)]

            return [self.source._get_relative(v) for v in target]
        else:
            return [self.config] if self.config else []

    def __repr__(self) -> str:
        return repr(
            {
                "event": self.event,
                "source": self.source.id,
                "target": [f"#{t.id}" for t in self.target],
                "cond": self.cond,
                "actions": self.actions,
                "type": self.type,
                "order": self.order,
            }
        )

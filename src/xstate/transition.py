from __future__ import annotations

import warnings
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

from xstate.action import Action, build_action
from xstate.event import Event

if TYPE_CHECKING:
    from xstate.state_node import StateNode

CondFunction = Callable[[Any, Event], bool]


class Transition:
    event: str | None
    source: StateNode
    config: str | StateNode
    actions: list[Action]
    cond: CondFunction | None
    order: int
    type: Literal["internal", "external"]

    def __init__(
        self,
        config: Any,
        source: StateNode,
        event: str | None,
        order: int,
        cond: CondFunction | None = None,
    ):
        self.event = event
        self.config = config
        self.source = source
        self.type = "external"
        # XState v5 renamed `cond` to `guard`; both are accepted for compat.
        self.cond = (
            config.get("guard", config.get("cond"))
            if isinstance(config, dict)
            else None
        )
        if isinstance(config, dict) and "cond" in config:
            warnings.warn(
                "`cond` is deprecated; use `guard` (XState v5 naming). "
                "`cond` still works but will be removed in a future release.",
                DeprecationWarning,
                stacklevel=2,
            )
        self.in_state = config.get("in", None) if isinstance(config, dict) else None
        self.order = order

        # Named actions resolve against the machine's `actions` registry, so a
        # named assign/raise/send is expanded to its real type and applied by
        # the engine in declared order (see action.build_action).
        self.actions = (
            [
                build_action(action, source.machine.actions)
                for action in config.get("actions", [])
            ]
            if isinstance(config, dict)
            else []
        )

    @property
    def target(self) -> list[StateNode]:
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
        return (
            f"Transition(event={self.event!r}, source={self.source.id!r},"
            f" target={[f'#{t.id}' for t in self.target]!r})"
        )

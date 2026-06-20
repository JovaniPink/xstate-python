from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from xstate.context import ContextAdapter
from xstate.machine import Machine


@dataclass(frozen=True, slots=True)
class MachineSetup:
    actions: dict[str, Any] = field(default_factory=dict)
    guards: dict[str, Any] = field(default_factory=dict)
    delays: dict[str, Any] = field(default_factory=dict)
    actors: dict[str, Any] = field(default_factory=dict)
    context_adapter: ContextAdapter | None = None

    def create_machine(
        self,
        config: dict[str, Any],
        *,
        actions: dict[str, Any] | None = None,
        guards: dict[str, Any] | None = None,
        delays: dict[str, Any] | None = None,
        actors: dict[str, Any] | None = None,
        context_adapter: ContextAdapter | None = None,
    ) -> Machine:
        return Machine(
            config,
            actions={**self.actions, **(actions or {})},
            guards={**self.guards, **(guards or {})},
            delays={**self.delays, **(delays or {})},
            actors={**self.actors, **(actors or {})},
            context_adapter=context_adapter or self.context_adapter,
            strict=True,
        )


def setup(
    *,
    actions: dict[str, Any] | None = None,
    guards: dict[str, Any] | None = None,
    delays: dict[str, Any] | None = None,
    actors: dict[str, Any] | None = None,
    context_adapter: ContextAdapter | None = None,
) -> MachineSetup:
    return MachineSetup(
        actions=actions or {},
        guards=guards or {},
        delays=delays or {},
        actors=actors or {},
        context_adapter=context_adapter,
    )

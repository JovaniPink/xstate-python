from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from xstate.context import ContextAdapter
from xstate.machine import Machine
from xstate.schema import MachineConfig

__all__ = ["MachineSetup", "setup"]


@dataclass(frozen=True, slots=True)
class MachineSetup[ContextT = Any, EventDataT = Any, OutputT = Any]:
    actions: dict[str, Any] = field(default_factory=dict)
    guards: dict[str, Any] = field(default_factory=dict)
    delays: dict[str, Any] = field(default_factory=dict)
    actors: dict[str, Any] = field(default_factory=dict)
    context_adapter: ContextAdapter[ContextT] | None = None

    def create_machine(
        self,
        config: MachineConfig[ContextT, EventDataT, OutputT] | dict[str, Any],
        *,
        actions: dict[str, Any] | None = None,
        guards: dict[str, Any] | None = None,
        delays: dict[str, Any] | None = None,
        actors: dict[str, Any] | None = None,
        context_adapter: ContextAdapter[ContextT] | None = None,
    ) -> Machine[ContextT, EventDataT, OutputT]:
        return Machine[ContextT, EventDataT, OutputT](
            config,
            actions={**self.actions, **(actions or {})},
            guards={**self.guards, **(guards or {})},
            delays={**self.delays, **(delays or {})},
            actors={**self.actors, **(actors or {})},
            context_adapter=context_adapter or self.context_adapter,
            strict=True,
        )


def setup[ContextT = Any, EventDataT = Any, OutputT = Any](
    *,
    actions: dict[str, Any] | None = None,
    guards: dict[str, Any] | None = None,
    delays: dict[str, Any] | None = None,
    actors: dict[str, Any] | None = None,
    context_adapter: ContextAdapter[ContextT] | None = None,
) -> MachineSetup[ContextT, EventDataT, OutputT]:
    return MachineSetup[ContextT, EventDataT, OutputT](
        actions=actions or {},
        guards=guards or {},
        delays=delays or {},
        actors=actors or {},
        context_adapter=context_adapter,
    )

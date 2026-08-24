from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from xstate.event import Event, RuntimeEventPayload

if TYPE_CHECKING:
    from xstate.state import State

__all__ = ["TransitionTrace", "MicrostepTrace", "MacrostepTrace"]


@dataclass(frozen=True, slots=True)
class TransitionTrace:
    """Portable summary of one selected transition."""

    event_type: str
    source_id: str
    target_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MicrostepTrace[ContextT = Any, EventDataT = Any, OutputT = Any]:
    """One immutable intermediate result inside a macrostep."""

    event: Event[RuntimeEventPayload[EventDataT, OutputT]]
    snapshot: State[ContextT, EventDataT, OutputT]
    transitions: tuple[TransitionTrace, ...]


@dataclass(frozen=True, slots=True)
class MacrostepTrace[ContextT = Any, EventDataT = Any, OutputT = Any]:
    """Settled result and ordered microsteps for one external event."""

    event: Event[EventDataT]
    previous_snapshot: State[ContextT, EventDataT, OutputT] | None
    snapshot: State[ContextT, EventDataT, OutputT]
    microsteps: tuple[MicrostepTrace[ContextT, EventDataT, OutputT], ...]

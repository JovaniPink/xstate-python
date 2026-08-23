from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = ["Event", "EventInput", "RuntimeEventPayload", "to_event"]

type EventInput[EventDataT = Any] = str | Event[EventDataT] | EventDataT
type RuntimeEventPayload[EventDataT = Any, OutputT = Any] = (
    EventDataT | OutputT | BaseException
)


@dataclass(slots=True, frozen=True)
class Event[PayloadT = Any]:
    name: str
    # Excluded from __hash__ so events with dict payloads remain hashable.
    # __eq__ still compares data, preserving the Python hash/eq contract.
    data: PayloadT | None = field(default=None, hash=False)


def to_event[EventDataT](event: EventInput[EventDataT]) -> Event[EventDataT]:
    """Normalize any event representation to an :class:`Event`."""
    if isinstance(event, Event):
        return event
    if isinstance(event, str):
        return Event(event)
    if isinstance(event, dict):
        return Event(event.get("type", ""), event)
    return Event(str(event))

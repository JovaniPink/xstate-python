from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class Event:
    name: str
    # Excluded from __hash__ so events with dict payloads remain hashable.
    # __eq__ still compares data, preserving the Python hash/eq contract.
    data: dict[str, Any] | None = field(default=None, hash=False)


def to_event(event: Any) -> Event:
    """Normalize any event representation to an :class:`Event`."""
    if isinstance(event, Event):
        return event
    if isinstance(event, str):
        return Event(event)
    if isinstance(event, dict):
        return Event(event.get("type", ""), event)
    return Event(str(event))

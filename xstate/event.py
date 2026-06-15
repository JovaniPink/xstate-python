from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class Event:
    name: str
    data: Optional[dict[str, Any]] = None


def to_event(event: Any) -> Event:
    """Normalize any event representation to an :class:`Event`."""
    if isinstance(event, Event):
        return event
    if isinstance(event, str):
        return Event(event)
    if isinstance(event, dict):
        return Event(event.get("type", ""), event)
    return Event(str(event))

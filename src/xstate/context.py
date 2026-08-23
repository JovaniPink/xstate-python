from __future__ import annotations

import copy
import dataclasses
from typing import Any, Protocol, cast

from xstate.exceptions import InvalidConfigError

__all__ = [
    "ContextAdapter",
    "DeepCopyContextAdapter",
    "DataclassContextAdapter",
    "dataclass_context",
]


class ContextAdapter[ContextT = Any](Protocol):
    def snapshot(self, context: ContextT) -> ContextT:
        """Return the context object used as the base for a new snapshot."""

    def apply(self, context: ContextT, updates: dict[str, Any]) -> ContextT:
        """Return context after applying assign updates."""


class DeepCopyContextAdapter[ContextT = Any]:
    """Default context policy: isolate snapshots with deepcopy, update by copy."""

    def snapshot(self, context: ContextT) -> ContextT:
        if context is None:
            return cast(ContextT, {})
        return copy.deepcopy(context)

    def apply(self, context: ContextT, updates: dict[str, Any]) -> ContextT:
        if isinstance(context, dict):
            next_context = dict(context)
            next_context.update(updates)
            return cast(ContextT, next_context)
        if dataclasses.is_dataclass(context) and not isinstance(context, type):
            return dataclasses.replace(context, **updates)
        raise InvalidConfigError(
            "assign() requires a dict context, a dataclass context, or a custom "
            "ContextAdapter."
        )


class DataclassContextAdapter[ContextT = Any]:
    """Context policy for immutable dataclass context values."""

    def snapshot(self, context: ContextT) -> ContextT:
        return context

    def apply(self, context: ContextT, updates: dict[str, Any]) -> ContextT:
        if not dataclasses.is_dataclass(context) or isinstance(context, type):
            raise InvalidConfigError(
                "DataclassContextAdapter requires a dataclass instance context."
            )
        return dataclasses.replace(context, **updates)


def dataclass_context[ContextT]() -> DataclassContextAdapter[ContextT]:
    return DataclassContextAdapter()

from __future__ import annotations

import copy
import dataclasses
from typing import Any, Protocol

from xstate.exceptions import InvalidConfigError


class ContextAdapter(Protocol):
    def snapshot(self, context: Any) -> Any:
        """Return the context object used as the base for a new snapshot."""

    def apply(self, context: Any, updates: dict[str, Any]) -> Any:
        """Return context after applying assign updates."""


class DeepCopyContextAdapter:
    """Default context policy: isolate snapshots with deepcopy, update by copy."""

    def snapshot(self, context: Any) -> Any:
        if context is None:
            return {}
        return copy.deepcopy(context)

    def apply(self, context: Any, updates: dict[str, Any]) -> Any:
        if isinstance(context, dict):
            next_context = dict(context)
            next_context.update(updates)
            return next_context
        if dataclasses.is_dataclass(context) and not isinstance(context, type):
            return dataclasses.replace(context, **updates)
        raise InvalidConfigError(
            "assign() requires a dict context, a dataclass context, or a custom "
            "ContextAdapter."
        )


class DataclassContextAdapter:
    """Context policy for immutable dataclass context values."""

    def snapshot(self, context: Any) -> Any:
        return context

    def apply(self, context: Any, updates: dict[str, Any]) -> Any:
        if not dataclasses.is_dataclass(context) or isinstance(context, type):
            raise InvalidConfigError(
                "DataclassContextAdapter requires a dataclass instance context."
            )
        return dataclasses.replace(context, **updates)


def dataclass_context() -> DataclassContextAdapter:
    return DataclassContextAdapter()

"""Composable guard helpers.

``and_``, ``or_``, and ``not_`` compose guards from smaller pieces without
writing wrapper lambdas.  Sub-guards can be callables or strings that reference
other named guards in the machine's ``guards`` registry.
``state_in`` / ``stateIn`` checks the current active state configuration.

Usage::

    from xstate import Machine, and_, not_, or_

    machine = Machine(config, guards={
        "isLoggedIn": lambda ctx, evt: ctx.get("logged_in"),
        "hasPermission": lambda ctx, evt: ctx.get("permission"),
        "canGo": and_("isLoggedIn", "hasPermission"),
    })

Or via the ``setup()`` builder (recommended)::

    from xstate import setup, and_

    machine = setup(guards={
        "isLoggedIn": lambda ctx, evt: ctx.get("logged_in"),
        "canGo": and_("isLoggedIn", lambda ctx, evt: ctx.get("value") > 0),
    }).create_machine(config)

String sub-guard names are resolved lazily from the machine's ``guards``
registry when the guard is evaluated by :func:`~xstate.algorithm.condition_match`.
"""

from __future__ import annotations

import inspect
from typing import Any

__all__ = ["and_", "or_", "not_", "state_in", "stateIn"]


class _ComposableGuard:
    """Base class for ``and_``, ``or_``, and ``not_`` guard combinators.

    Instances are callable (``guard(context, event)``) and can be registered
    directly in the machine's ``guards`` dict.
    """

    def _eval(
        self,
        guard: Any,
        context: Any,
        event: Any,
        registry: dict,
        state: Any | None = None,
    ) -> bool:
        if isinstance(guard, str):
            fn = registry.get(guard)
            if fn is None:
                raise KeyError(
                    f"Composable guard references unknown guard '{guard}'. "
                    "Make sure it is registered in the machine's guards dict."
                )
            guard = fn
        if isinstance(guard, _ComposableGuard):
            return guard._call(context, event, registry, state=state)
        from xstate.handlers import invoke_handler

        return bool(invoke_handler(guard, context, event, state=state))

    def _call(
        self,
        context: Any,
        event: Any,
        registry: dict,
        state: Any | None = None,
    ) -> bool:
        raise NotImplementedError

    def __call__(self, context: Any = None, event: Any = None) -> bool:
        """Direct call (no registry — string sub-guards must not be used)."""
        return self._call(context, event, {})


class _AndGuard(_ComposableGuard):
    """Guard that passes when **all** sub-guards pass."""

    def __init__(self, guards: tuple[Any, ...]):
        self._guards = guards

    def _call(
        self,
        context: Any,
        event: Any,
        registry: dict,
        state: Any | None = None,
    ) -> bool:
        return all(
            self._eval(g, context, event, registry, state=state) for g in self._guards
        )


class _OrGuard(_ComposableGuard):
    """Guard that passes when **any** sub-guard passes."""

    def __init__(self, guards: tuple[Any, ...]):
        self._guards = guards

    def _call(
        self,
        context: Any,
        event: Any,
        registry: dict,
        state: Any | None = None,
    ) -> bool:
        return any(
            self._eval(g, context, event, registry, state=state) for g in self._guards
        )


class _NotGuard(_ComposableGuard):
    """Guard that passes when its sub-guard does **not** pass."""

    def __init__(self, guard: Any):
        self._guard = guard

    def _call(
        self,
        context: Any,
        event: Any,
        registry: dict,
        state: Any | None = None,
    ) -> bool:
        return not self._eval(
            self._guard,
            context,
            event,
            registry,
            state=state,
        )


class _StateInGuard(_ComposableGuard):
    """Guard that passes when the active state configuration matches a spec."""

    __signature__ = inspect.Signature(
        [
            inspect.Parameter(
                "args",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]
    )

    def __init__(self, state_value: Any):
        self._state_value = state_value

    def _call(
        self,
        context: Any,
        event: Any,
        registry: dict,
        state: Any | None = None,
    ) -> bool:
        if state is None:
            return False
        from xstate.algorithm import _matches_in_state

        return _matches_in_state(self._state_value, state)

    def __call__(self, context: Any = None, event: Any = None) -> bool:
        if hasattr(context, "state"):
            return self._call(
                context.context,
                context.event,
                {},
                state=context.state,
            )
        return self._call(context, event, {})


def and_(*guards: Any) -> _AndGuard:
    """Return a guard that passes when ALL of *guards* pass."""
    return _AndGuard(guards)


def or_(*guards: Any) -> _OrGuard:
    """Return a guard that passes when ANY of *guards* passes."""
    return _OrGuard(guards)


def not_(guard: Any) -> _NotGuard:
    """Return a guard that passes when *guard* does NOT pass."""
    return _NotGuard(guard)


def state_in(state_value: Any) -> _StateInGuard:
    """Return a guard that passes when the current state matches *state_value*."""
    return _StateInGuard(state_value)


def stateIn(state_value: Any) -> _StateInGuard:
    """XState-compatible alias for :func:`state_in`."""
    return state_in(state_value)

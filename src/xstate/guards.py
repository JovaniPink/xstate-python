"""Composable guard combinators (0.6.0).

``and_``, ``or_``, and ``not_`` compose guards from smaller pieces without
writing wrapper lambdas.  Sub-guards can be callables or strings that reference
other named guards in the machine's ``guards`` registry.

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

from typing import Any


class _ComposableGuard:
    """Base class for ``and_``, ``or_``, and ``not_`` guard combinators.

    Instances are callable (``guard(context, event)``) and can be registered
    directly in the machine's ``guards`` dict.
    """

    def _eval(self, guard: Any, context: Any, event: Any, registry: dict) -> bool:
        if isinstance(guard, str):
            fn = registry.get(guard)
            if fn is None:
                raise KeyError(
                    f"Composable guard references unknown guard '{guard}'. "
                    "Make sure it is registered in the machine's guards dict."
                )
            guard = fn
        if isinstance(guard, _ComposableGuard):
            return guard._call(context, event, registry)
        from xstate.handlers import invoke_handler

        return bool(invoke_handler(guard, context, event))

    def _call(self, context: Any, event: Any, registry: dict) -> bool:
        raise NotImplementedError

    def __call__(self, context: Any = None, event: Any = None) -> bool:
        """Direct call (no registry — string sub-guards must not be used)."""
        return self._call(context, event, {})


class _AndGuard(_ComposableGuard):
    """Guard that passes when **all** sub-guards pass."""

    def __init__(self, guards: tuple[Any, ...]):
        self._guards = guards

    def _call(self, context: Any, event: Any, registry: dict) -> bool:
        return all(self._eval(g, context, event, registry) for g in self._guards)


class _OrGuard(_ComposableGuard):
    """Guard that passes when **any** sub-guard passes."""

    def __init__(self, guards: tuple[Any, ...]):
        self._guards = guards

    def _call(self, context: Any, event: Any, registry: dict) -> bool:
        return any(self._eval(g, context, event, registry) for g in self._guards)


class _NotGuard(_ComposableGuard):
    """Guard that passes when its sub-guard does **not** pass."""

    def __init__(self, guard: Any):
        self._guard = guard

    def _call(self, context: Any, event: Any, registry: dict) -> bool:
        return not self._eval(self._guard, context, event, registry)


def and_(*guards: Any) -> _AndGuard:
    """Return a guard that passes when ALL of *guards* pass."""
    return _AndGuard(guards)


def or_(*guards: Any) -> _OrGuard:
    """Return a guard that passes when ANY of *guards* passes."""
    return _OrGuard(guards)


def not_(guard: Any) -> _NotGuard:
    """Return a guard that passes when *guard* does NOT pass."""
    return _NotGuard(guard)

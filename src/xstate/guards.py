"""Composable guard combinators (0.6.0) + ``stateIn`` guard (0.7.0).

``and_``, ``or_``, and ``not_`` compose guards from smaller pieces without
writing wrapper lambdas.  Sub-guards can be callables, strings that reference
other named guards in the machine's ``guards`` registry, or other composable
guards (including :func:`stateIn`).

``stateIn`` is a guard over the *current configuration* — it passes when the
machine is in the given state — and composes with the combinators above.

Usage::

    from xstate import Machine, and_, not_, or_, stateIn

    machine = Machine(config, guards={
        "isLoggedIn": lambda ctx, evt: ctx.get("logged_in"),
        "hasPermission": lambda ctx, evt: ctx.get("permission"),
        "canGo": and_("isLoggedIn", "hasPermission", stateIn("#ready")),
    })

Or via the ``setup()`` builder (recommended)::

    from xstate import setup, and_, stateIn

    machine = setup(guards={
        "isLoggedIn": lambda ctx, evt: ctx.get("logged_in"),
        "canGo": and_("isLoggedIn", stateIn("ready")),
    }).create_machine(config)

String sub-guard names are resolved lazily from the machine's ``guards``
registry when the guard is evaluated by :func:`~xstate.algorithm.condition_match`.
"""

from __future__ import annotations

from typing import Any


class _ComposableGuard:
    """Base class for ``and_``, ``or_``, ``not_``, and ``stateIn`` guards.

    Instances are callable (``guard(context, event)``) and can be registered
    directly in the machine's ``guards`` dict.  Evaluation threads the active
    ``configuration`` through so nested ``stateIn`` sub-guards can see it.
    """

    def _eval(
        self,
        guard: Any,
        context: Any,
        event: Any,
        registry: dict,
        configuration: Any = None,
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
            return guard._call(context, event, registry, configuration)
        from xstate.handlers import invoke_handler

        return bool(invoke_handler(guard, context, event))

    def _call(
        self,
        context: Any,
        event: Any,
        registry: dict,
        configuration: Any = None,
    ) -> bool:
        raise NotImplementedError

    def __call__(self, context: Any = None, event: Any = None) -> bool:
        """Direct call (no registry/configuration — for standalone use)."""
        return self._call(context, event, {}, None)


class _AndGuard(_ComposableGuard):
    """Guard that passes when **all** sub-guards pass."""

    def __init__(self, guards: tuple[Any, ...]):
        self._guards = guards

    def _call(
        self, context: Any, event: Any, registry: dict, configuration: Any = None
    ) -> bool:
        return all(
            self._eval(g, context, event, registry, configuration)
            for g in self._guards
        )


class _OrGuard(_ComposableGuard):
    """Guard that passes when **any** sub-guard passes."""

    def __init__(self, guards: tuple[Any, ...]):
        self._guards = guards

    def _call(
        self, context: Any, event: Any, registry: dict, configuration: Any = None
    ) -> bool:
        return any(
            self._eval(g, context, event, registry, configuration)
            for g in self._guards
        )


class _NotGuard(_ComposableGuard):
    """Guard that passes when its sub-guard does **not** pass."""

    def __init__(self, guard: Any):
        self._guard = guard

    def _call(
        self, context: Any, event: Any, registry: dict, configuration: Any = None
    ) -> bool:
        return not self._eval(self._guard, context, event, registry, configuration)


class _StateInGuard(_ComposableGuard):
    """Guard that passes when the machine is in the given state (v5 ``stateIn``).

    The *spec* uses the same syntax as a transition ``in`` guard: ``"#id"`` for
    an explicit id, a dotted ``"parent.child"`` path, or a ``{parent: child}``
    dict.  Evaluation needs the active configuration; when called without one
    (e.g. directly, outside a transition) it returns ``False``.
    """

    def __init__(self, spec: Any):
        self._spec = spec

    def _call(
        self, context: Any, event: Any, registry: dict, configuration: Any = None
    ) -> bool:
        if configuration is None:
            return False
        from xstate.algorithm import _matches_in_state

        return _matches_in_state(self._spec, configuration)


def and_(*guards: Any) -> _AndGuard:
    """Return a guard that passes when ALL of *guards* pass."""
    return _AndGuard(guards)


def or_(*guards: Any) -> _OrGuard:
    """Return a guard that passes when ANY of *guards* passes."""
    return _OrGuard(guards)


def not_(guard: Any) -> _NotGuard:
    """Return a guard that passes when *guard* does NOT pass."""
    return _NotGuard(guard)


def stateIn(spec: Any) -> _StateInGuard:
    """Return a guard that passes when the machine is currently in *spec*.

    *spec* is ``"#id"``, a dotted ``"parent.child"`` path, or a ``{parent: child}``
    dict — the same shape accepted by a transition ``in`` guard.
    """
    return _StateInGuard(spec)

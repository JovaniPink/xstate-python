from __future__ import annotations

import functools
import inspect
import warnings
from dataclasses import dataclass
from typing import Any

from xstate.event import Event
from xstate.exceptions import InvalidConfigError

_UNSET = object()


@dataclass(frozen=True, slots=True)
class HandlerArgs:
    context: Any
    event: Event | None
    params: Any | None = None


@dataclass(frozen=True, slots=True)
class GuardReference:
    name: str
    params: Any | None = None
    path: str | None = None


@functools.lru_cache(maxsize=1024)
def _get_params(fn: Any) -> tuple[inspect.Parameter, ...] | None:
    try:
        return tuple(inspect.signature(fn).parameters.values())
    except (TypeError, ValueError):
        return None


def _annotation_is_handler_args(annotation: Any) -> bool:
    if annotation is HandlerArgs:
        return True
    if annotation is inspect.Parameter.empty:
        return False
    annotation_text = annotation if isinstance(annotation, str) else str(annotation)
    return "HandlerArgs" in annotation_text


def _looks_like_handler_args_param(param: inspect.Parameter) -> bool:
    return param.name in {"args", "arg", "scope", "handler_args"} or (
        _annotation_is_handler_args(param.annotation)
    )


class HandlerAdapter:
    """One-time callable adapter for XState-style handler functions.

    The adapter preserves legacy xstate-python call styles while letting new code
    use the canonical Python form ``handler(HandlerArgs(...))``. Signature
    inspection happens when a machine is built, not during transition selection.
    """

    fn: Any
    kind: str
    strict: bool
    default_params: Any | None
    path: str | None
    _mode: str

    def __init__(
        self,
        fn: Any,
        *,
        kind: str = "handler",
        strict: bool = False,
        params: Any | None = None,
        path: str | None = None,
    ) -> None:
        if isinstance(fn, HandlerAdapter):
            self.fn = fn.fn
            self.kind = fn.kind
            self.strict = fn.strict or strict
            self.default_params = params if params is not None else fn.default_params
            self.path = path if path is not None else fn.path
            self._mode = fn._mode
            return

        if not callable(fn):
            raise InvalidConfigError(
                f"{kind} at {path or '<unknown>'} must be callable, got {type(fn)!r}."
            )

        self.fn = fn
        self.kind = kind
        self.strict = strict
        self.default_params = params
        self.path = path
        self._mode = self._select_mode(fn)
        if strict and self._mode.startswith("legacy"):
            warnings.warn(
                f"{kind} at {path or '<unknown>'} uses a legacy callable "
                "signature; prefer handler(HandlerArgs(context, event, params)).",
                DeprecationWarning,
                stacklevel=3,
            )

    def _select_mode(self, fn: Any) -> str:
        params = _get_params(fn)
        if params is None:
            return "legacy_context_event"

        if any(p.kind == p.VAR_KEYWORD for p in params):
            if self.kind.startswith("action") and all(
                p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD) for p in params
            ):
                return "legacy_zero"
            return "keyword"

        kw_only = [p for p in params if p.kind == p.KEYWORD_ONLY]
        if kw_only:
            return "legacy_keyword"

        if any(p.kind == p.VAR_POSITIONAL for p in params):
            return "legacy_context_event"

        positional = [
            p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        if len(positional) == 0:
            return "legacy_zero"
        if len(positional) == 1:
            return (
                "args"
                if _looks_like_handler_args_param(positional[0])
                else "legacy_context"
            )
        if len(positional) == 2 and _looks_like_handler_args_param(positional[0]):
            return "args_params"
        return "legacy_context_event"

    def __call__(
        self,
        context: Any,
        event: Event | None,
        *,
        params: Any = _UNSET,
    ) -> Any:
        call_params = self.default_params if params is _UNSET else params
        args = HandlerArgs(context=context, event=event, params=call_params)

        if self._mode == "args":
            return self.fn(args)
        if self._mode == "args_params":
            return self.fn(args, call_params)
        if self._mode == "keyword":
            return self.fn(context=context, event=event, params=call_params)
        if self._mode == "legacy_keyword":
            kwargs: dict[str, Any] = {}
            kw_names = {
                p.name for p in (_get_params(self.fn) or ()) if p.kind == p.KEYWORD_ONLY
            }
            if "context" in kw_names:
                kwargs["context"] = context
            if "event" in kw_names:
                kwargs["event"] = event
            if "params" in kw_names:
                kwargs["params"] = call_params
            return self.fn(**kwargs)
        if self._mode == "legacy_zero":
            return self.fn()
        if self._mode == "legacy_context":
            return self.fn(context)
        return self.fn(context, event)


def adapt_handler(
    value: Any,
    *,
    kind: str,
    strict: bool,
    params: Any | None = None,
    path: str | None = None,
) -> Any:
    if callable(value):
        return HandlerAdapter(
            value,
            kind=kind,
            strict=strict,
            params=params,
            path=path,
        )
    return value


def invoke_handler(
    fn: Any,
    context: Any,
    event: Event | None,
    *,
    params: Any = _UNSET,
) -> Any:
    if isinstance(fn, HandlerAdapter):
        return fn(context, event, params=params)

    # Compatibility shim for truly opaque callables. New machines should pass
    # through HandlerAdapter at parse/setup time so this is not the hot path.
    return HandlerAdapter(fn)(context, event, params=params)

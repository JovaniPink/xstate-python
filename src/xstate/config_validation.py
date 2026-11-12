"""Static key validation for XState JSON-shaped machine configs.

The default ``Machine(config)`` boundary stays permissive so ordinary XState
JSON keeps loading. This module powers the opt-in strict check: it walks a raw
config and reports keys the library does not understand, separating

* ``unsupported`` keys: real XState keys this library does not implement yet
  (for example ``reenter``), which would otherwise be silently ignored and
  change behavior, from
* ``unknown`` keys: names XState does not define at that position (usually typos).

It performs no resolution and has no dependency on the rest of the engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

__all__ = ["ConfigIssue", "find_config_issues"]

_STATE_KEYS = frozenset(
    {
        "id",
        "type",
        "tags",
        "meta",
        "description",
        "initial",
        "states",
        "on",
        "always",
        "entry",
        "exit",
        "after",
        "invoke",
        "onDone",
        "history",
        "target",
        "output",
        "data",
    }
)
_ROOT_ONLY_KEYS = frozenset(
    {"context", "options", "version", "schemas", "types", "delays"}
)
_TRANSITION_KEYS = frozenset(
    {"target", "actions", "guard", "cond", "type", "in", "description", "meta"}
)
_INVOKE_KEYS = frozenset(
    {"id", "src", "input", "onDone", "onError", "onSnapshot", "systemId"}
)

# Real XState keys that this library does not implement; ignoring them silently
# would change machine behavior.
_UNSUPPORTED_TRANSITION_KEYS = frozenset({"reenter"})
_UNSUPPORTED_INVOKE_KEYS = frozenset({"autoForward"})


@dataclass(frozen=True)
class ConfigIssue:
    """One problem found while statically validating a machine config."""

    code: Literal["unknown_key", "unsupported_key"]
    path: str
    key: str
    message: str


def find_config_issues(config: dict[str, Any]) -> list[ConfigIssue]:
    """Return every unknown or unsupported key in ``config``, in document order."""

    issues: list[ConfigIssue] = []
    _check_state(config, "config", issues, is_root=True)
    return issues


def _report(
    issues: list[ConfigIssue],
    path: str,
    key: str,
    unsupported: frozenset[str],
    kind: str,
) -> None:
    if key in unsupported:
        issues.append(
            ConfigIssue(
                "unsupported_key",
                path,
                key,
                f"{path}: '{key}' is an XState {kind} key that xstate-python "
                "does not implement yet; it would be ignored.",
            )
        )
    else:
        issues.append(
            ConfigIssue(
                "unknown_key",
                path,
                key,
                f"{path}: unknown {kind} key '{key}'.",
            )
        )


def _check_state(
    node: Any, path: str, issues: list[ConfigIssue], *, is_root: bool = False
) -> None:
    if not isinstance(node, dict):
        return
    allowed = _STATE_KEYS | _ROOT_ONLY_KEYS if is_root else _STATE_KEYS
    for key in node:
        if isinstance(key, str) and key not in allowed:
            _report(issues, path, key, frozenset(), "state")

    states = node.get("states")
    if isinstance(states, dict):
        for name, child in states.items():
            _check_state(child, f"{path}.states.{name}", issues)

    for field in ("on", "after"):
        mapping = node.get(field)
        if isinstance(mapping, dict):
            for event, value in mapping.items():
                _check_transitions(value, f"{path}.{field}[{event!r}]", issues)
    for field in ("always", "onDone"):
        _check_transitions(node.get(field), f"{path}.{field}", issues)

    invoke = node.get("invoke")
    invokes = invoke if isinstance(invoke, list) else [invoke]
    for index, item in enumerate(invokes):
        if isinstance(item, dict):
            _check_invoke(item, f"{path}.invoke[{index}]", issues)


def _check_transitions(value: Any, path: str, issues: list[ConfigIssue]) -> None:
    items = value if isinstance(value, list) else [value]
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        item_path = f"{path}[{index}]" if isinstance(value, list) else path
        for key in item:
            if isinstance(key, str) and key not in _TRANSITION_KEYS:
                _report(
                    issues, item_path, key, _UNSUPPORTED_TRANSITION_KEYS, "transition"
                )


def _check_invoke(item: dict[str, Any], path: str, issues: list[ConfigIssue]) -> None:
    for key in item:
        if isinstance(key, str) and key not in _INVOKE_KEYS:
            _report(issues, path, key, _UNSUPPORTED_INVOKE_KEYS, "invoke")
    for field in ("onDone", "onError", "onSnapshot"):
        _check_transitions(item.get(field), f"{path}.{field}", issues)

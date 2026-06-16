from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

from xstate.algorithm import get_state_value, is_in_final_state
from xstate.event import to_event
from xstate.exceptions import InvalidConfigError

if TYPE_CHECKING:
    from xstate.action import Action
    from xstate.state_node import StateNode


class State:
    configuration: set[StateNode]
    value: str
    context: dict[str, Any]
    actions: list[Callable | Action]
    history_value: dict[str, set[StateNode]]
    status: Literal["active", "done", "error"]
    output: Any | None
    error: Any | None
    event: (
        Any | None
    )  # stamped by Interpreter; None when produced by machine.transition

    def __init__(
        self,
        configuration: set[StateNode],
        context: dict[str, Any],
        actions: list[Callable | Action] | None = None,
        history_value: dict[str, set[StateNode]] | None = None,
    ):
        if not configuration:
            raise InvalidConfigError("State requires a non-empty configuration.")
        root = next(iter(configuration)).machine.root
        self.configuration = configuration
        self.value = get_state_value(root, configuration)
        self.context = context
        self.actions = actions if actions is not None else []
        self.history_value = history_value if history_value is not None else {}
        self.error = None
        self.event = None

        # A machine is "done" when the root state has reached a final
        # configuration. is_in_final_state handles both compound roots (a
        # direct final child is active) and parallel roots (all regions are in
        # a final state).
        if is_in_final_state(root, configuration):
            self.status = "done"
            # For compound roots the final child carries donedata; parallel
            # roots have no single output value.
            final_child = next(
                (s for s in configuration if s.type == "final" and s.parent is root),
                None,
            )
            self.output = final_child.donedata if final_child else None
        else:
            self.status = "active"
            self.output = None

    def can(self, event: Any) -> bool:
        """Return True if any enabled transition exists for *event* right now.

        Respects guards and the current context, so the result reflects whether
        the machine would actually move on this event — not just whether any
        transition is configured for it.
        """
        from xstate.algorithm import select_transitions

        transitions = select_transitions(
            event=to_event(event),
            configuration=self.configuration,
            context=self.context,
            history_value=self.history_value,
        )
        return len(transitions) > 0

    def matches(self, value: Any) -> bool:
        """Return True if the current state value matches *value*.

        Accepts a string (exact match) or a dict describing a partial nested
        value, e.g. ``state.matches({"loading": "data"})``.
        """
        if isinstance(value, str):
            return self.value == value
        if isinstance(value, dict):
            return _matches_dict(self.value, value)
        return False

    def __repr__(self) -> str:
        return (
            f"State(value={self.value!r}, status={self.status!r},"
            f" context={self.context!r})"
        )


def _matches_dict(state_value: Any, pattern: Any) -> bool:
    if isinstance(pattern, str):
        return bool(state_value == pattern)
    if not isinstance(pattern, dict) or not isinstance(state_value, dict):
        return False
    return all(
        k in state_value and _matches_dict(state_value[k], v)
        for k, v in pattern.items()
    )


# XState v5 public alias.
MachineSnapshot = State

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set, Union

from xstate.algorithm import get_state_value

if TYPE_CHECKING:
    from xstate.action import Action
    from xstate.state_node import StateNode


class State:
    configuration: Set[StateNode]
    value: str
    context: Dict[str, Any]
    actions: List[Union[Callable, "Action"]]
    history_value: Dict[str, Set[StateNode]]
    status: str   # "active" | "done" | "error"
    output: Optional[Any]
    error: Optional[Any]

    def __init__(
        self,
        configuration: Set[StateNode],
        context: Dict[str, Any],
        actions: List[Union[Callable, "Action"]] = [],
        history_value: Optional[Dict[str, Set[StateNode]]] = None,
    ):
        root = next(iter(configuration)).machine.root
        self.configuration = configuration
        self.value = get_state_value(root, configuration)
        self.context = context
        self.actions = actions
        self.history_value = history_value if history_value is not None else {}
        self.error = None

        # A machine is "done" when the active atomic state is a final child of
        # the root compound node (root.parent is None; its children have
        # parent.parent is None).
        final = next(
            (
                s
                for s in configuration
                if s.type == "final"
                and s.parent is not None
                and s.parent.parent is None
            ),
            None,
        )
        if final is not None:
            self.status = "done"
            self.output = final.donedata
        else:
            self.status = "active"
            self.output = None

    def matches(self, value) -> bool:
        """Return True if the current state value matches *value*.

        Accepts a string (exact match) or a dict describing a partial nested
        value, e.g. ``state.matches({"loading": "data"})``.
        """
        if isinstance(value, str):
            return self.value == value
        if isinstance(value, dict):
            return _matches_dict(self.value, value)
        return False

    def __repr__(self):
        return repr(
            {
                "value": self.value,
                "context": self.context,
                "status": self.status,
                "output": self.output,
            }
        )


def _matches_dict(state_value, pattern) -> bool:
    if isinstance(pattern, str):
        return state_value == pattern
    if not isinstance(pattern, dict) or not isinstance(state_value, dict):
        return False
    return all(
        k in state_value and _matches_dict(state_value[k], v)
        for k, v in pattern.items()
    )


# XState v5 public alias.
MachineSnapshot = State

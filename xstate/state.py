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

    def __repr__(self):
        return repr(
            {
                "value": self.value,
                "context": self.context,
                "actions": self.actions,
            }
        )

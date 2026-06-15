import copy
import warnings
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from xstate.action import INTERPRETER_TYPES
from xstate.algorithm import (
    enter_states,
    get_configuration_from_state,
    main_event_loop,
    main_event_loop2,
)
from xstate.event import Event
from xstate.state import State
from xstate.state_node import StateNode


class Machine:
    id: str
    root: StateNode
    _id_map: Dict[str, StateNode]
    config: Dict[str, Any]
    states: Dict[str, StateNode]
    actions: Dict[str, Callable]
    guards: Dict[str, Callable]
    delays: Dict[str, Any]
    actors: Dict[str, Any]
    _order: int

    def __init__(
        self,
        config: Dict[str, Any],
        actions: Optional[Dict[str, Any]] = None,
        guards: Optional[Dict[str, Callable]] = None,
        delays: Optional[Dict[str, Any]] = None,
        actors: Optional[Dict[str, Any]] = None,
    ):
        if "id" not in config:
            raise ValueError(
                "Machine config must include an 'id' key. "
                "Example: Machine({'id': 'myMachine', 'initial': ..., 'states': {...}})"
            )
        self.id = config["id"]
        self._id_map = {}
        self._order = 0
        # Registries must be populated *before* the state tree is built: node and
        # transition construction resolves named actions against `self.actions`
        # (see action.build_action), so a named assign/raise/send is expanded to
        # its real type and applied by the engine in declared order.
        self.actions = actions if actions is not None else {}
        self.guards = guards if guards is not None else {}
        self.delays = delays if delays is not None else {}
        # Named actor logic referenced by `invoke: {"src": "<name>"}`; resolved
        # by the actor layer when an invoking state is entered.
        self.actors = actors if actors is not None else {}
        self.root = StateNode(
            config, machine=self, key=config.get("id", "(machine)"), parent=None
        )
        self.states = self.root.states
        self.config = config
        self.context = config.get("context", {}) or {}

    def _get_order(self) -> int:
        order = self._order
        self._order += 1
        return order

    def _to_event(self, event) -> Event:
        if isinstance(event, Event):
            return event
        if isinstance(event, str):
            return Event(event)
        if isinstance(event, dict):
            return Event(event.get("type", ""), event)
        return Event(str(event))

    def transition(self, state: State, event):
        event = self._to_event(event)
        configuration = get_configuration_from_state(
            from_node=self.root, state_value=state.value, partial_configuration=set()
        )
        context = copy.deepcopy(state.context) if state.context else {}
        history_value = dict(state.history_value) if state.history_value else {}
        configuration, _actions = main_event_loop(
            configuration, event, context, history_value
        )

        actions, unknown = self._get_actions(_actions)
        self._warn_unknown_actions(unknown)

        return State(
            configuration=configuration,
            context=context,
            actions=actions,
            history_value=history_value,
        )

    def _get_actions(
        self, actions: List
    ) -> Tuple[List[Union[Callable, Any]], List[str]]:
        """Resolve resolved-engine actions for the caller.

        Assigns and raises were already applied/queued by the SCXML engine and
        do not reach here. What remains is: interpreter-owned actions (send /
        cancel / send_parent / send_to — passed through as raw ``Action`` for
        the interpreter), named side-effect callables (resolved to the callable
        registered in ``self.actions``), and inline callables. Names with no
        implementation are collected in ``unknown`` so the caller can warn.
        """
        result: List[Union[Callable, Any]] = []
        unknown: List[str] = []
        for action in actions:
            if action.type in INTERPRETER_TYPES:
                # Passed through as raw Action; the interpreter handles them.
                result.append(action)
            elif action.type in self.actions:
                result.append(self.actions[action.type])
            elif callable(action.type):
                result.append(action.type)
            else:
                unknown.append(str(action.type))
        return result, unknown

    def _warn_unknown_actions(self, unknown: List[str]) -> None:
        """Warn once per action name that has no registered implementation."""
        for name in unknown:
            warnings.warn(
                f"No implementation found for action '{name}'. "
                f"Pass it via Machine(config, actions={{'{name}': ...}}).",
                UserWarning,
                stacklevel=3,
            )

    def state_from(self, state_value) -> State:
        configuration = set(self._get_configuration(state_value=state_value))
        return State(configuration=configuration, context={})

    def _register(self, state_node: StateNode):
        state_node.machine = self
        self._id_map[state_node.id] = state_node

    def _get_by_id(self, id: str) -> Optional[StateNode]:
        return self._id_map.get(id, None)

    def _get_configuration(self, state_value, parent=None) -> List[StateNode]:
        if parent is None:
            parent = self.root

        if isinstance(state_value, str):
            state_node = parent.states.get(state_value, None)

            if state_node is None:
                raise ValueError(f"State node {state_value} is missing")

            return [state_node]

        configuration = []

        for key in state_value.keys():
            state_node = parent.states.get(key)
            configuration.append(state_node)

            configuration += self._get_configuration(
                state_value.get(key), parent=state_node
            )

        return configuration

    @property
    def initial_state(self) -> State:
        context = copy.deepcopy(self.context)
        history_value: Dict[str, Any] = {}
        init_event = Event("xstate.init")
        configuration, _actions, internal_queue = enter_states(
            [self.root.initial],
            configuration=set(),
            states_to_invoke=set(),
            history_value=history_value,
            actions=[],
            internal_queue=[],
            context=context,
            event=init_event,
        )

        configuration, _actions = main_event_loop2(
            configuration=configuration,
            actions=_actions,
            internal_queue=internal_queue,
            context=context,
            event=init_event,
            history_value=history_value,
        )

        actions, unknown = self._get_actions(_actions)
        self._warn_unknown_actions(unknown)

        return State(
            configuration=configuration,
            context=context,
            actions=actions,
            history_value=history_value,
        )

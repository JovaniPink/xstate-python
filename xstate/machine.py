from typing import Dict, List
from xstate.state_node import StateNode
from xstate.state import State
from xstate.algorithm import (
    enter_states,
    get_configuration_from_state,
    get_state_value,
    main_event_loop,
    main_event_loop2,
)
from xstate.event import Event


class Machine:
    id: str
    root: StateNode
    _id_map: Dict[str, StateNode]
    config: object
    states: Dict[str, StateNode]
    actions: List[lambda: None]
    _order: int

    def __init__(self, config: object, actions={}, guards={}):
        self.id = config["id"]
        self._id_map = {}
        self._order = 0
        self.root = StateNode(
            config, machine=self, key=config.get("id", "(machine)"), parent=None
        )
        self.states = self.root.states
        self.config = config
        self.actions = actions
        self.guards = guards
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
            return Event(event.get("type"), event)
        return Event(event)

    def transition(self, state: State, event):
        event = self._to_event(event)
        configuration = get_configuration_from_state(
            from_node=self.root, state_value=state.value, partial_configuration=set()
        )
        context = dict(state.context) if state.context else {}
        history_value = dict(state.history_value) if state.history_value else {}
        configuration, _actions = main_event_loop(
            configuration, event, context, history_value
        )

        actions, warnings = self._get_actions(_actions)
        for w in warnings:
            print(w)

        return State(
            configuration=configuration,
            context=context,
            actions=actions,
            history_value=history_value,
        )

    def _get_actions(self, actions) -> List[lambda: None]:
        result = []
        errors = []
        for action in actions:
            if action.type in self.actions:
                result.append(self.actions[action.type])
            elif callable(action.type):
                result.append(action.type)
            else:
                errors.append("No '{}' action".format(action.type))
        return result, errors

    def state_from(self, state_value) -> State:
        configuration = self._get_configuration(state_value=state_value)

        return State(configuration=configuration, context=None)

    def _register(self, state_node: StateNode):
        state_node.machine = self
        self._id_map[state_node.id] = state_node

    def _get_by_id(self, id: str) -> StateNode:
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
        context = dict(self.context)
        history_value = {}
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

        actions, warnings = self._get_actions(_actions)
        for w in warnings:
            print(w)

        return State(
            configuration=configuration,
            context=context,
            actions=actions,
            history_value=history_value,
        )

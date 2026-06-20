from __future__ import annotations

import functools
import warnings
from collections import deque
from collections.abc import Callable
from typing import Any

from xstate.action import INTERPRETER_TYPES, Action
from xstate.algorithm import (
    enter_states,
    get_configuration_from_state,
    main_event_loop,
    main_event_loop2,
)
from xstate.config_parser import StateNodeConfigParser
from xstate.context import ContextAdapter, DeepCopyContextAdapter
from xstate.event import Event, to_event
from xstate.exceptions import InvalidConfigError, UnregisteredImplementationError
from xstate.handlers import HandlerAdapter, adapt_handler
from xstate.state import State
from xstate.state_node import StateNode

__all__ = ["Machine"]

type ActionCallable = Callable[[], Any]
type ResolvedAction = Action | ActionCallable


class Machine:
    id: str
    root: StateNode
    _id_map: dict[str, StateNode]
    config: dict[str, Any]
    states: dict[str, StateNode]
    actions: dict[str, Any]
    guards: dict[str, Any]
    delays: dict[str, Any]
    actors: dict[str, Any]
    _order: int
    strict: bool
    context_adapter: ContextAdapter

    def __init__(
        self,
        config: dict[str, Any],
        actions: dict[str, Any] | None = None,
        guards: dict[str, Any] | None = None,
        delays: dict[str, Any] | None = None,
        actors: dict[str, Any] | None = None,
        context_adapter: ContextAdapter | None = None,
        strict: bool = False,
    ):
        if "id" not in config:
            raise InvalidConfigError(
                "Machine config must include an 'id' key. "
                "Example: Machine({'id': 'myMachine', 'initial': ..., 'states': {...}})"
            )
        self.id = config["id"]
        self._id_map = {}
        self._order = 0
        self.strict = strict
        self.context_adapter = context_adapter or DeepCopyContextAdapter()
        # Registries must be populated *before* the state tree is built: node and
        # transition construction resolves named actions against `self.actions`
        # (see action.build_action), so a named assign/raise/send is expanded to
        # its real type and applied by the engine in declared order.
        self.actions = self._adapt_registry(actions or {}, kind="action")
        self.guards = self._adapt_registry(guards or {}, kind="guard")
        self.delays = self._adapt_registry(delays or {}, kind="delay")
        # Named actor logic referenced by `invoke: {"src": "<name>"}`; resolved
        # by the actor layer when an invoking state is entered.
        self.actors = actors if actors is not None else {}
        self.root = StateNodeConfigParser(self).parse(config)
        self.states = self.root.states
        self.config = config
        self.context = (
            config.get("context") if config.get("context") is not None else {}
        )

    def _adapt_registry(self, registry: dict[str, Any], *, kind: str) -> dict[str, Any]:
        return {
            name: adapt_handler(
                value,
                kind=f"{kind} '{name}'",
                strict=self.strict,
                path=f"{kind}s.{name}",
            )
            for name, value in registry.items()
        }

    def _get_order(self) -> int:
        order = self._order
        self._order += 1
        return order

    def _to_event(self, event: Any) -> Event:
        return to_event(event)

    def transition(self, state: State, event: Any) -> State:
        event = self._to_event(event)
        configuration = get_configuration_from_state(
            from_node=self.root, state_value=state.value, partial_configuration=set()
        )
        context = self.context_adapter.snapshot(state.context)
        history_value = {
            state_id: set(states) for state_id, states in state.history_value.items()
        }
        configuration, _actions, context = main_event_loop(
            configuration, event, context, history_value
        )

        actions, unknown = self._get_actions(_actions, context, event)
        self._warn_unknown_actions(unknown)

        return State(
            configuration=configuration,
            context=context,
            actions=actions,
            history_value=history_value,
        )

    def _get_actions(
        self, actions: list[Action], context: Any, event: Event | None
    ) -> tuple[list[ResolvedAction], list[str]]:
        """Resolve resolved-engine actions for the caller.

        Assigns and raises were already applied/queued by the SCXML engine and
        do not reach here. What remains is: interpreter-owned actions (send /
        cancel / send_parent / send_to — passed through as raw ``Action`` for
        the interpreter), named side-effect callables (resolved to the callable
        registered in ``self.actions``), and inline callables. Names with no
        implementation are collected in ``unknown`` so the caller can warn.
        """
        result: list[ResolvedAction] = []
        unknown: list[str] = []
        for action in actions:
            if action.type in INTERPRETER_TYPES:
                # Passed through as raw Action; the interpreter handles them.
                result.append(action)
            elif action.type in self.actions:
                result.append(
                    self._bind_action(
                        action,
                        self.actions[action.type],
                        context,
                        event,
                    )
                )
            elif callable(action.type):
                result.append(self._bind_action(action, action.type, context, event))
            else:
                unknown.append(str(action.type))
        return result, unknown

    def _bind_action(
        self,
        action: Any,
        implementation: Any,
        context: Any,
        event: Event | None,
    ) -> ActionCallable:
        params = action.data.get("params") if hasattr(action, "data") else None
        if isinstance(implementation, HandlerAdapter):
            return functools.partial(implementation, context, event, params=params)
        if callable(implementation):
            adapter = HandlerAdapter(implementation, kind="action")
            return functools.partial(adapter, context, event, params=params)
        raise InvalidConfigError(
            f"Action implementation for '{action.type}' is not callable."
        )

    def _warn_unknown_actions(self, unknown: list[str]) -> None:
        """Warn once per action name that has no registered implementation."""
        for name in unknown:
            warnings.warn(
                f"No implementation found for action '{name}'. "
                f"Pass it via Machine(config, actions={{'{name}': ...}}).",
                UnregisteredImplementationError,
                stacklevel=3,
            )

    def state_from(self, state_value: Any) -> State:
        configuration = set(self._get_configuration(state_value=state_value))
        return State(configuration=configuration, context={})

    def _register(self, state_node: StateNode) -> None:
        state_node.machine = self
        self._id_map[state_node.id] = state_node

    def _get_by_id(self, id: str) -> StateNode | None:
        return self._id_map.get(id, None)

    def _get_configuration(
        self, state_value: Any, parent: StateNode | None = None
    ) -> list[StateNode]:
        if parent is None:
            parent = self.root

        if isinstance(state_value, str):
            state_node = parent.states.get(state_value, None)

            if state_node is None:
                raise InvalidConfigError(f"State node '{state_value}' is missing")

            return [state_node]

        configuration: list[StateNode] = []

        for key in state_value:
            state_node = parent.states.get(key)
            if state_node is None:
                raise InvalidConfigError(f"State node '{key}' is missing")
            configuration.append(state_node)
            configuration += self._get_configuration(
                state_value.get(key), parent=state_node
            )

        return configuration

    @property
    def initial_state(self) -> State:
        context = self.context_adapter.snapshot(self.context)
        history_value: dict[str, Any] = {}
        init_event = Event("xstate.init")
        configuration, _actions, internal_queue, context = enter_states(
            [self.root.initial],
            configuration=set(),
            states_to_invoke=set(),
            history_value=history_value,
            actions=[],
            internal_queue=deque(),
            context=context,
            event=init_event,
        )

        configuration, _actions, context = main_event_loop2(
            configuration=configuration,
            actions=_actions,
            internal_queue=internal_queue,
            context=context,
            event=init_event,
            history_value=history_value,
        )

        actions, unknown = self._get_actions(_actions, context, init_event)
        self._warn_unknown_actions(unknown)

        return State(
            configuration=configuration,
            context=context,
            actions=actions,
            history_value=history_value,
        )

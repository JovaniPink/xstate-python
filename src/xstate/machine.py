from __future__ import annotations

import functools
import warnings
from collections.abc import Callable
from typing import Any, cast

from xstate.action import INTERPRETER_TYPES, Action
from xstate.algorithm import (
    AlgorithmMicrostep,
    MacrostepResult,
    initial_event_loop,
    main_event_loop,
)
from xstate.config_parser import StateNodeConfigParser
from xstate.context import ContextAdapter, DeepCopyContextAdapter
from xstate.event import Event, EventInput, RuntimeEventPayload, to_event
from xstate.exceptions import InvalidConfigError, UnregisteredImplementationError
from xstate.handlers import HandlerAdapter, adapt_handler
from xstate.schema import MachineConfig
from xstate.state import State
from xstate.state_node import StateNode
from xstate.trace import MacrostepTrace, MicrostepTrace, TransitionTrace

__all__ = ["Machine", "get_microsteps", "get_initial_microsteps"]

ActionCallable = Callable[[], Any]
ResolvedAction = Action | ActionCallable


class Machine[ContextT = Any, EventDataT = Any, OutputT = Any]:
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
    context: ContextT
    context_adapter: ContextAdapter[ContextT]
    max_iterations: int | None

    def __init__(
        self,
        config: MachineConfig[ContextT, EventDataT, OutputT] | dict[str, Any],
        actions: dict[str, Any] | None = None,
        guards: dict[str, Any] | None = None,
        delays: dict[str, Any] | None = None,
        actors: dict[str, Any] | None = None,
        context_adapter: ContextAdapter[ContextT] | None = None,
        strict: bool = False,
        max_iterations: int | None = None,
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
        options = config.get("options")
        if options is not None and not isinstance(options, dict):
            raise InvalidConfigError("Machine options must be a dict.")
        configured_limit = (
            options.get("maxIterations") if isinstance(options, dict) else None
        )
        effective_limit = (
            max_iterations if max_iterations is not None else configured_limit
        )
        self.max_iterations = self._validate_max_iterations(effective_limit)
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
        raw_config = cast(dict[str, Any], config)
        self.root = StateNodeConfigParser(self).parse(raw_config)
        self.states = self.root.states
        self.config = raw_config
        self.context = cast(
            ContextT,
            config.get("context") if config.get("context") is not None else {},
        )

    @staticmethod
    def _validate_max_iterations(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise InvalidConfigError(
                "options.maxIterations and max_iterations must be a non-negative "
                "integer or None."
            )
        return cast(int, value)

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

    def _to_event(self, event: EventInput[EventDataT]) -> Event[EventDataT]:
        return to_event(event)

    def transition(
        self,
        state: State[ContextT, EventDataT, OutputT],
        event: EventInput[EventDataT],
    ) -> State[ContextT, EventDataT, OutputT]:
        next_state, _event, _result = self._transition_core(
            state, event, capture_microsteps=False
        )
        return next_state

    def _transition_with_trace(
        self,
        state: State[ContextT, EventDataT, OutputT],
        event: EventInput[EventDataT],
    ) -> tuple[
        State[ContextT, EventDataT, OutputT],
        MacrostepTrace[ContextT, EventDataT, OutputT],
    ]:
        next_state, event_object, result = self._transition_core(
            state, event, capture_microsteps=True
        )
        trace = MacrostepTrace[ContextT, EventDataT, OutputT](
            event=event_object,
            previous_snapshot=state,
            snapshot=next_state,
            microsteps=self._build_microstep_traces(result.microsteps),
        )
        return next_state, trace

    def _transition_core(
        self,
        state: State[ContextT, EventDataT, OutputT],
        event: EventInput[EventDataT],
        *,
        capture_microsteps: bool,
    ) -> tuple[
        State[ContextT, EventDataT, OutputT],
        Event[EventDataT],
        MacrostepResult[ContextT, Any],
    ]:
        event_object = self._to_event(event)
        configuration = set(state.configuration)
        if any(node.machine is not self for node in configuration):
            raise InvalidConfigError(
                f"State snapshot does not belong to machine '{self.id}'."
            )
        context = self.context_adapter.snapshot(state.context)
        history_value = {
            state_id: set(states) for state_id, states in state.history_value.items()
        }
        result = main_event_loop(
            configuration,
            event_object,
            context,
            history_value=history_value,
            context_snapshot=self.context_adapter.snapshot,
            machine_id=self.id,
            max_iterations=self.max_iterations,
            capture_microsteps=capture_microsteps,
        )

        actions, unknown = self._get_actions(
            result.actions, result.context, event_object
        )
        self._warn_unknown_actions(unknown)

        next_state = State[ContextT, EventDataT, OutputT](
            configuration=result.configuration,
            context=result.context,
            actions=actions,
            history_value=history_value,
            output=result.output,
        )
        return next_state, event_object, result

    def _build_microstep_traces(
        self,
        microsteps: tuple[AlgorithmMicrostep[ContextT, Any], ...],
    ) -> tuple[MicrostepTrace[ContextT, EventDataT, OutputT], ...]:
        result: list[MicrostepTrace[ContextT, EventDataT, OutputT]] = []
        for microstep in microsteps:
            actions, _unknown = self._get_actions(
                list(microstep.actions), microstep.context, microstep.event
            )
            snapshot = State[ContextT, EventDataT, OutputT](
                configuration=microstep.configuration,
                context=microstep.context,
                actions=actions,
                history_value=microstep.history_value,
                output=cast(OutputT | None, microstep.output),
            )
            result.append(
                MicrostepTrace[ContextT, EventDataT, OutputT](
                    event=cast(
                        Event[RuntimeEventPayload[EventDataT, OutputT]],
                        microstep.event,
                    ),
                    snapshot=snapshot,
                    transitions=tuple(
                        TransitionTrace(
                            event_type=transition.event or "",
                            source_id=transition.source.id,
                            target_ids=tuple(target.id for target in transition.target),
                        )
                        for transition in microstep.transitions
                    ),
                )
            )
        return tuple(result)

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

    def state_from(self, state_value: Any) -> State[ContextT, EventDataT, OutputT]:
        configuration = set(self._get_configuration(state_value=state_value))
        return State[ContextT, EventDataT, OutputT](
            configuration=configuration,
            context=cast(ContextT, {}),
        )

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
    def initial_state(self) -> State[ContextT, EventDataT, OutputT]:
        state, _event, _result = self._initial_transition_core(capture_microsteps=False)
        return state

    def _initial_transition(
        self,
    ) -> tuple[
        State[ContextT, EventDataT, OutputT],
        MacrostepTrace[ContextT, EventDataT, OutputT],
    ]:
        state, init_event, result = self._initial_transition_core(
            capture_microsteps=True
        )
        trace = MacrostepTrace[ContextT, EventDataT, OutputT](
            event=init_event,
            previous_snapshot=None,
            snapshot=state,
            microsteps=self._build_microstep_traces(result.microsteps),
        )
        return state, trace

    def _initial_transition_core(
        self, *, capture_microsteps: bool
    ) -> tuple[
        State[ContextT, EventDataT, OutputT],
        Event[EventDataT],
        MacrostepResult[ContextT, OutputT],
    ]:
        context = self.context_adapter.snapshot(self.context)
        history_value: dict[str, Any] = {}
        result: MacrostepResult[ContextT, OutputT] = initial_event_loop(
            self.root.initial,
            context,
            history_value=history_value,
            context_snapshot=self.context_adapter.snapshot,
            machine_id=self.id,
            max_iterations=self.max_iterations,
            capture_microsteps=capture_microsteps,
        )
        init_event: Event[EventDataT] = Event("xstate.init")

        actions, unknown = self._get_actions(result.actions, result.context, init_event)
        self._warn_unknown_actions(unknown)

        state = State[ContextT, EventDataT, OutputT](
            configuration=result.configuration,
            context=result.context,
            actions=actions,
            history_value=history_value,
            output=result.output,
        )
        return state, init_event, result


def get_microsteps[ContextT, EventDataT, OutputT](
    machine: Machine[ContextT, EventDataT, OutputT],
    snapshot: State[ContextT, EventDataT, OutputT],
    event: EventInput[EventDataT],
) -> tuple[MicrostepTrace[ContextT, EventDataT, OutputT], ...]:
    """Return immutable microstep traces for one pure machine transition."""
    _state, trace = machine._transition_with_trace(snapshot, event)
    return trace.microsteps


def get_initial_microsteps[ContextT, EventDataT, OutputT](
    machine: Machine[ContextT, EventDataT, OutputT],
) -> tuple[MicrostepTrace[ContextT, EventDataT, OutputT], ...]:
    """Return immutable microstep traces for machine initialization."""
    _state, trace = machine._initial_transition()
    return trace.microsteps

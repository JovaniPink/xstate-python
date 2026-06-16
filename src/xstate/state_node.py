from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from xstate.action import Action, build_action
from xstate.exceptions import InvalidConfigError
from xstate.transition import Transition

if TYPE_CHECKING:
    from xstate.machine import Machine


class StateNode:
    on: dict[str, list[Transition]]
    machine: Machine
    parent: StateNode | None
    entry: list[Action]
    exit: list[Action]
    donedata: dict | None
    type: Literal["atomic", "compound", "parallel", "final", "history"]
    transitions: list[Transition]
    id: str
    key: str
    states: dict[str, StateNode]
    order: int
    after: list[tuple]
    invoke: list[dict]

    def __init__(  # noqa: C901
        self,
        # { "type": "compound", "states": { ... } }
        config,
        machine: Machine,
        key: str,
        parent: StateNode | None = None,
    ):
        self.order = machine._get_order()
        self.config = config
        self.parent: StateNode | None = parent
        self.machine = machine
        self.id = (
            config.get("id", parent.id + "." + key)
            if parent
            else config.get("id", machine.id + "." + key)
        )
        self.entry = (
            [self.get_actions(entry_action) for entry_action in config.get("entry")]
            if config.get("entry")
            else []
        )

        self.exit = (
            [self.get_actions(exit_action) for exit_action in config.get("exit")]
            if config.get("exit")
            else []
        )

        self.key = key
        self.states = {
            k: StateNode(v, machine=machine, parent=self, key=k)
            for k, v in config.get("states", {}).items()
        }
        self.on = {}
        self.transitions = []
        for k, v in config.get("on", {}).items():
            self.on[k] = []
            transition_configs = v if isinstance(v, list) else [v]

            for transition_config in transition_configs:
                transition = Transition(
                    transition_config,
                    source=self,
                    event=k,
                    order=self.machine._get_order(),
                )
                self.on[k].append(transition)
                self.transitions.append(transition)

        # `always:` is XState v5 syntax for eventless transitions (v4: on: {"": ...}).
        # Both forms populate self.on[""] so the algorithm handles them identically.
        always_configs = config.get("always")
        if always_configs is not None:
            if not isinstance(always_configs, list):
                always_configs = [always_configs]
            self.on.setdefault("", [])
            for always_config in always_configs:
                transition = Transition(
                    always_config,
                    source=self,
                    event="",
                    order=self.machine._get_order(),
                )
                self.on[""].append(transition)
                self.transitions.append(transition)

        self.type = config.get("type")

        if self.type is None:
            self.type = "atomic" if not self.states else "compound"

        # History state support. A history state restores the most recent
        # configuration of its parent; "shallow" (default) restores only the
        # parent's immediate child, "deep" restores the full descendant path.
        # `transition` holds the default target used on the first entry, before
        # any history has been recorded.
        self.history = (
            config.get("history", "shallow") if self.type == "history" else None
        )
        self.transition = None
        if self.type == "history" and config.get("target") is not None:
            self.transition = Transition(
                config.get("target"), source=self, event=None, order=-1
            )

        # XState v5 renamed `data` to `output` on final states; both accepted.
        self.donedata = (
            config.get("output", config.get("data")) if self.type == "final" else None
        )

        if config.get("onDone"):
            done_event = f"done.state.{self.id}"
            done_configs = config.get("onDone")
            if not isinstance(done_configs, list):
                done_configs = [done_configs]
            self.on[done_event] = []
            for done_config in done_configs:
                done_transition = Transition(
                    done_config,
                    source=self,
                    event=done_event,
                    order=self.machine._get_order(),
                )
                self.on[done_event].append(done_transition)
                self.transitions.append(done_transition)

        # Invoked actors. `invoke` runs a child actor for the lifetime of this
        # state. Each invocation is normalised to a descriptor
        # {"id", "src", "input", ...}; `onDone` / `onError` become transitions
        # keyed by the generated `done.invoke.<id>` / `error.platform.<id>`
        # events that the actor layer feeds back when the child completes.
        # `self.invoke` lets the actor layer discover which invocations a node
        # owns (mirroring `self.after` for delayed transitions).
        self.invoke: list[dict] = []
        invoke_configs = config.get("invoke")
        if invoke_configs is not None:
            if not isinstance(invoke_configs, list):
                invoke_configs = [invoke_configs]
            for index, invoke_config in enumerate(invoke_configs):
                raw_id = invoke_config.get("id")
                invoke_id = (
                    raw_id if raw_id is not None else f"{self.id}:invocation[{index}]"
                )
                src = invoke_config.get("src")
                if src is None:
                    raise InvalidConfigError(
                        f"invoke on state '{self.id}' is missing a 'src'. "
                        f"Provide actor logic or a name registered via "
                        f"Machine(config, actors={{...}})."
                    )
                descriptor = {
                    "id": invoke_id,
                    "src": src,
                    "input": invoke_config.get("input"),
                }
                self.invoke.append(descriptor)

                for event_name, key in (
                    (f"done.invoke.{invoke_id}", "onDone"),
                    (f"error.platform.{invoke_id}", "onError"),
                ):
                    handler = invoke_config.get(key)
                    if handler is None:
                        continue
                    handler_configs = (
                        handler if isinstance(handler, list) else [handler]
                    )
                    self.on.setdefault(event_name, [])
                    for handler_config in handler_configs:
                        transition = Transition(
                            handler_config,
                            source=self,
                            event=event_name,
                            order=self.machine._get_order(),
                        )
                        self.on[event_name].append(transition)
                        self.transitions.append(transition)

        # Delayed transitions. `after` maps a delay (ms number or a delay-ref
        # string resolved from Machine(delays=...)) to a transition. Each becomes
        # a normal transition keyed by a generated event
        # `xstate.after(<delay>)#<id>` that the interpreter schedules on entry
        # and cancels on exit. `self.after` lets the interpreter discover which
        # delays a node owns.
        self.after: list[tuple] = []
        for delay, transition_config in config.get("after", {}).items():
            after_event = f"xstate.after({delay})#{self.id}"
            transition_configs = (
                transition_config
                if isinstance(transition_config, list)
                else [transition_config]
            )
            self.on[after_event] = []
            for tc in transition_configs:
                transition = Transition(
                    tc,
                    source=self,
                    event=after_event,
                    order=self.machine._get_order(),
                )
                self.on[after_event].append(transition)
                self.transitions.append(transition)
            self.after.append((delay, after_event))

        machine._register(self)

    def get_actions(self, action):
        # Named actions are resolved against the machine's `actions` registry so
        # a named assign/raise/send is expanded to its real type and applied by
        # the engine in declared order (see action.build_action).
        return build_action(action, self.machine.actions)

    @property
    def history_states(self) -> list[StateNode]:
        """Child states of this node that are history pseudo-states."""
        return [s for s in self.states.values() if s.type == "history"]

    @property
    def initial(self) -> Transition:
        initial_key = self.config.get("initial")

        if not initial_key:
            if self.type == "compound":
                return Transition(
                    next(iter(self.states.values())), source=self, event=None, order=-1
                )
            if self.type == "parallel":
                # Entering a parallel state enters all of its regions; target the
                # node itself so add_descendent_states_to_enter fans out to them.
                return Transition(self, source=self, event=None, order=-1)
            raise InvalidConfigError(
                f"State '#{self.id}' of type '{self.type}' has no initial state."
            )

        target = self.states.get(initial_key)
        if target is None:
            raise InvalidConfigError(
                f"Initial state '{initial_key}' is not a child of '#{self.id}'."
            )
        return Transition(target, source=self, event=None, order=-1)

    def _get_relative(self, target: str) -> StateNode:
        if target.startswith("#"):
            node = self.machine._get_by_id(target[1:])
            if node is None:
                raise InvalidConfigError(
                    f"No state with id '{target[1:]}' in machine '{self.machine.id}'"
                )
            return node

        if self.parent is None:
            raise InvalidConfigError(
                f"Cannot resolve relative target '{target}' from root state "
                f"node '#{self.id}'"
            )
        state_node = self.parent.states.get(target)

        if not state_node:
            raise InvalidConfigError(
                f"Relative state node '{target}' does not exist on state "
                f"node '#{self.id}'"
            )

        return state_node

    def __repr__(self) -> str:
        return f"<StateNode {{'id': {self.id!r}}}>"

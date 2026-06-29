from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from collections.abc import Set as AbstractSet
from typing import Any

from xstate.action import (
    ASSIGN_TYPE,
    CHOOSE_TYPE,
    PURE_TYPE,
    RAISE_TYPE,
    Action,
    build_action,
)
from xstate.event import Event
from xstate.exceptions import UnregisteredImplementationError
from xstate.handlers import GuardReference, invoke_handler
from xstate.state_node import StateNode
from xstate.transition import Transition

HistoryValue = dict[str, set[StateNode]]
ReadOnlyHistoryValue = Mapping[str, AbstractSet[StateNode]]


def _invoke(fn, context: dict | None, event: Event | None) -> Any:
    """Compatibility shim for arity-aware callables.

    New machines adapt handlers at parse/setup time via ``HandlerAdapter``.
    This remains for tests and for opaque callables that enter through public
    extension points outside the parser.
    """
    return invoke_handler(fn, context, event)


def _apply_assignment(action: Action, context: Any, event: Event | None) -> Any:
    """Return context with the updates produced by an assign action applied."""
    if context is None:
        return context
    assignment = action.data.get("assignment", {})
    if callable(assignment):
        updates = _invoke(assignment, context, event) or {}
    else:
        updates = {}
        for key, value in assignment.items():
            updates[key] = _invoke(value, context, event) if callable(value) else value

    adapter = action.data.get("_context_adapter")
    if adapter is not None:
        return adapter.apply(context, updates)
    if isinstance(context, dict):
        next_context = dict(context)
        next_context.update(updates)
        return next_context
    return context


def compute_entry_set(
    transitions: list[Transition],
    states_to_enter: set[StateNode],
    states_for_default_entry: set[StateNode],
    default_history_content: dict,
    history_value: HistoryValue,
):
    for t in transitions:
        for s in t.target:
            add_descendent_states_to_enter(
                s,
                states_to_enter=states_to_enter,
                states_for_default_entry=states_for_default_entry,
                default_history_content=default_history_content,
                history_value=history_value,
            )
        ancestor = get_transition_domain(t, history_value=history_value)
        for s in get_effective_target_states(t, history_value=history_value):
            add_ancestor_states_to_enter(
                s,
                ancestor=ancestor,
                states_to_enter=states_to_enter,
                states_for_default_entry=states_for_default_entry,
                default_history_content=default_history_content,
                history_value=history_value,
            )


def add_descendent_states_to_enter(
    state: StateNode,
    states_to_enter: set[StateNode],
    states_for_default_entry: set[StateNode],
    default_history_content: dict,
    history_value: HistoryValue,
):
    if is_history_state(state):
        # A history pseudo-state is always a child of a compound state.
        parent = state.parent
        assert parent is not None
        restored = history_value.get(state.id)
        if restored:
            for s in restored:
                add_descendent_states_to_enter(
                    s,
                    states_to_enter=states_to_enter,
                    states_for_default_entry=states_for_default_entry,
                    default_history_content=default_history_content,
                    history_value=history_value,
                )
            for s in restored:
                # Per SCXML the ancestor bound is the history node's parent, not
                # each restored state's parent. For deep history `s` can be a
                # nested atomic descendant, so using `s.parent` would drop the
                # intermediate ancestors between `s` and `state.parent`.
                add_ancestor_states_to_enter(
                    s,
                    ancestor=parent,
                    states_to_enter=states_to_enter,
                    states_for_default_entry=states_for_default_entry,
                    default_history_content=default_history_content,
                    history_value=history_value,
                )
        else:
            # No history recorded yet: enter the history state's default target
            # (or, if none is configured, fall back to the parent's initial).
            default_transition = state.transition or parent.initial
            default_history_content[parent.id] = default_transition
            for s in default_transition.target:
                add_descendent_states_to_enter(
                    s,
                    states_to_enter=states_to_enter,
                    states_for_default_entry=states_for_default_entry,
                    default_history_content=default_history_content,
                    history_value=history_value,
                )
            for s in default_transition.target:
                # Ancestor bound is the history node's parent (see note above):
                # a deeply-nested default target must still enter every ancestor
                # up to `state.parent`.
                add_ancestor_states_to_enter(
                    s,
                    ancestor=parent,
                    states_to_enter=states_to_enter,
                    states_for_default_entry=states_for_default_entry,
                    default_history_content=default_history_content,
                    history_value=history_value,
                )
    else:
        states_to_enter.add(state)
        if is_compound_state(state):
            states_for_default_entry.add(state)
            for s in state.initial.target:
                add_descendent_states_to_enter(
                    s,
                    states_to_enter=states_to_enter,
                    states_for_default_entry=states_for_default_entry,
                    default_history_content=default_history_content,
                    history_value=history_value,
                )
            for s in state.initial.target:
                add_ancestor_states_to_enter(
                    s,
                    ancestor=s.parent,
                    states_to_enter=states_to_enter,
                    states_for_default_entry=states_for_default_entry,
                    default_history_content=default_history_content,
                    history_value=history_value,
                )
        else:
            if is_parallel_state(state):
                for child in get_child_states(state):
                    if not any(is_descendent(s, child) for s in states_to_enter):
                        add_descendent_states_to_enter(
                            child,
                            states_to_enter=states_to_enter,
                            states_for_default_entry=states_for_default_entry,
                            default_history_content=default_history_content,
                            history_value=history_value,
                        )


def is_history_state(state: StateNode) -> bool:
    return state.type == "history"


def is_compound_state(state: StateNode) -> bool:
    return state.type == "compound"


def is_atomic_state(state: StateNode) -> bool:
    return any(
        state.type == state_type for state_type in ["atomic", "final", "history"]
    )


def is_descendent(state: StateNode, state2: StateNode | None) -> bool:
    marker = state

    while marker.parent and marker.parent != state2:
        marker = marker.parent

    return marker.parent == state2


# function getTransitionDomain(t)
#     tstates = getEffectiveTargetStates(t)
#     if not tstates:
#         return null
#     elif t.type == "internal" and isCompoundState(t.source) \
#          and tstates.every(lambda s: isDescendant(s,t.source)):
#         return t.source
#     else:
#         return findLCCA([t.source].append(tstates))
def get_transition_domain(
    transition: Transition, history_value: ReadOnlyHistoryValue
) -> StateNode | None:
    tstates = get_effective_target_states(transition, history_value=history_value)
    if not tstates:
        return None
    elif (
        transition.type == "internal"
        and is_compound_state(transition.source)
        and all(is_descendent(s, state2=transition.source) for s in tstates)
    ):
        return transition.source
    else:
        return find_lcca([transition.source] + list(tstates))


def find_lcca(state_list: list[StateNode]) -> StateNode | None:
    for anc in get_proper_ancestors(state_list[0], state2=None):
        if all(is_descendent(s, state2=anc) for s in state_list[1:]):
            return anc
    return None


def get_effective_target_states(
    transition: Transition, history_value: ReadOnlyHistoryValue
) -> set[StateNode]:
    targets: set[StateNode] = set()

    for s in transition.target:
        if is_history_state(s):
            recorded = history_value.get(s.id)
            if recorded:
                targets.update(recorded)
            else:
                # No recorded history: resolve the default target, falling back
                # to the parent's initial transition when none is configured.
                parent = s.parent
                assert parent is not None
                default_transition = s.transition or parent.initial
                targets.update(
                    get_effective_target_states(
                        default_transition, history_value=history_value
                    )
                )
        else:
            targets.add(s)

    return targets


# procedure addAncestorStatesToEnter(state, ancestor, statesToEnter,
#                                    statesForDefaultEntry, defaultHistoryContent)
#     for anc in getProperAncestors(state,ancestor):
#         statesToEnter.add(anc)
#         if isParallelState(anc):
#             for child in getChildStates(anc):
#                 if not statesToEnter.some(lambda s: isDescendant(s,child)):
#                     addDescendantStatesToEnter(child, statesToEnter,
#                         statesForDefaultEntry, defaultHistoryContent)
def add_ancestor_states_to_enter(
    state: StateNode,
    ancestor: StateNode | None,
    states_to_enter: set[StateNode],
    states_for_default_entry: set[StateNode],
    default_history_content: dict,
    history_value: HistoryValue,
):
    for anc in get_proper_ancestors(state, state2=ancestor):
        states_to_enter.add(anc)
        if is_parallel_state(anc):
            for child in get_child_states(anc):
                if not any(is_descendent(s, state2=child) for s in states_to_enter):
                    add_descendent_states_to_enter(
                        child,
                        states_to_enter=states_to_enter,
                        states_for_default_entry=states_for_default_entry,
                        default_history_content=default_history_content,
                        history_value=history_value,
                    )


def get_proper_ancestors(
    state1: StateNode, state2: StateNode | None
) -> list[StateNode]:
    # Per W3C SCXML getProperAncestors: return the ancestors of state1 in
    # ancestry order, up to *but not including* state2 (state2 is the exclusive
    # upper bound / transition domain). When state2 is None, return all
    # ancestors up to the root.
    ancestors: list[StateNode] = []
    marker = state1.parent
    while marker and marker != state2:
        ancestors.append(marker)
        marker = marker.parent

    return ancestors


def is_final_state(state_node: StateNode) -> bool:
    return state_node.type == "final"


def is_parallel_state(state_node: StateNode | None) -> bool:
    # A null node (e.g. the root's absent parent) is never parallel.
    return state_node is not None and state_node.type == "parallel"


def get_child_states(state_node: StateNode) -> list[StateNode]:
    # Per W3C SCXML, getChildStates returns the real <state>/<parallel>/<final>
    # children and explicitly excludes <history> (and <initial>) pseudo-states.
    # Excluding history here keeps every region-enumeration caller correct: the
    # parallel entry fan-out, is_in_final_state, and the parallel onDone check.
    return [s for s in state_node.states.values() if not is_history_state(s)]


def is_in_final_state(state: StateNode, configuration: AbstractSet[StateNode]) -> bool:
    if is_compound_state(state):
        return any(
            is_final_state(s) and (s in configuration) for s in get_child_states(state)
        )
    elif is_parallel_state(state):
        return all(is_in_final_state(s, configuration) for s in get_child_states(state))
    else:
        return False


def enter_states(
    enabled_transitions: list[Transition],
    configuration: set[StateNode],
    states_to_invoke: set[StateNode],
    history_value: HistoryValue,
    actions: list[Action],
    internal_queue: deque[Event],
    context: dict | None = None,
    event: Event | None = None,
) -> tuple[set[StateNode], list[Action], deque[Event], Any]:
    states_to_enter: set[StateNode] = set()
    states_for_default_entry: set[StateNode] = set()

    default_history_content: dict = {}

    compute_entry_set(
        enabled_transitions,
        states_to_enter=states_to_enter,
        states_for_default_entry=states_for_default_entry,
        default_history_content=default_history_content,
        history_value=history_value,
    )

    # TODO: sort
    for s in list(states_to_enter):
        configuration.add(s)
        states_to_invoke.add(s)

        # if binding == "late" and s.isFirstEntry:
        #     initializeDataModel(datamodel.s,doc.s)
        #     s.isFirstEntry = false

        # TODO: sort
        for action in s.entry:
            context = execute_content(
                action,
                actions=actions,
                internal_queue=internal_queue,
                context=context,
                event=event,
            )
        if s in states_for_default_entry:
            # executeContent(s.initial.transition)
            continue
        if default_history_content.get(s.id) is not None:
            # executeContent(defaultHistoryContent[s.id])
            continue
        if is_final_state(s):
            parent = s.parent
            assert parent is not None  # a final state always has a parent
            grandparent = parent.parent
            donedata = (
                _invoke(s.donedata, context, event)
                if callable(s.donedata)
                else s.donedata
            )
            internal_queue.append(Event(f"done.state.{parent.id}", donedata))

            if (
                grandparent is not None
                and is_parallel_state(grandparent)
                and all(
                    is_in_final_state(parent_state, configuration)
                    for parent_state in get_child_states(grandparent)
                )
            ):
                internal_queue.append(Event(f"done.state.{grandparent.id}"))

    return (configuration, actions, internal_queue, context)


def exit_states(
    enabled_transitions: list[Transition],
    configuration: set[StateNode],
    states_to_invoke: set[StateNode],
    history_value: HistoryValue,
    actions: list[Action],
    internal_queue: deque[Event],
    context: dict | None = None,
    event: Event | None = None,
):
    states_to_exit = compute_exit_set(
        enabled_transitions, configuration=configuration, history_value=history_value
    )
    for s in states_to_exit:
        states_to_invoke.discard(s)

    # Record history before exiting: for each history child of a state being
    # exited, snapshot the part of the current configuration it should restore.
    # "deep" remembers the full atomic descendant path; "shallow" remembers only
    # the state's immediate active children.
    for s in states_to_exit:
        for h in s.history_states:
            if h.history == "deep":
                history_value[h.id] = {
                    s0
                    for s0 in configuration
                    if is_atomic_state(s0) and is_descendent(s0, state2=s)
                }
            else:
                history_value[h.id] = {s0 for s0 in configuration if s0.parent == s}

    for s in states_to_exit:
        for action in s.exit:
            context = execute_content(
                action,
                actions=actions,
                internal_queue=internal_queue,
                context=context,
                event=event,
            )
        # for inv in s.invoke:
        #     cancelInvoke(inv)
        configuration.remove(s)

    return (
        configuration,
        actions,
        context,
    )


def compute_exit_set(
    enabled_transitions: list[Transition],
    configuration: AbstractSet[StateNode],
    history_value: ReadOnlyHistoryValue,
) -> set[StateNode]:
    states_to_exit: set[StateNode] = set()
    for t in enabled_transitions:
        if t.target:
            domain = get_transition_domain(t, history_value=history_value)
            for s in configuration:
                if is_descendent(s, state2=domain):
                    states_to_exit.add(s)

    return states_to_exit


def name_match(event: str, specific_event: str) -> bool:
    return event == specific_event


def _matches_in_state(in_spec, configuration: AbstractSet[StateNode]) -> bool:
    """Return True if ``in_spec`` matches the current configuration.

    ``in_spec`` is the value of an XState ``in`` transition guard:
    - str ``"#id"``   — true if a state with that id is active
    - str ``"a.b"``   — true if the state keyed "b" whose parent is keyed "a" is active
    - dict ``{k: v}`` — true if all k/v pairs are satisfied (each a one-level path)
    """
    if isinstance(in_spec, str):
        if in_spec.startswith("#"):
            target_id = in_spec[1:]
            return any(s.id == target_id for s in configuration)
        parts = in_spec.split(".")
        if len(parts) == 1:
            return any(s.key == parts[0] for s in configuration)

        # Walk parts as an ancestor chain: parts[-1] must be active and its
        # ancestors must match the remaining parts in order.
        def _path_active(parts: list[str]) -> bool:
            leaf_key = parts[-1]
            for s in configuration:
                if s.key != leaf_key:
                    continue
                node: StateNode | None = s
                matched = True
                for ancestor_key in reversed(parts[:-1]):
                    assert node is not None  # guaranteed by the break below
                    node = node.parent
                    if node is None or node.key != ancestor_key:
                        matched = False
                        break
                if matched:
                    return True
            return False

        return _path_active(parts)
    if isinstance(in_spec, dict):
        return all(
            _matches_in_state(f"{parent_key}.{child_key}", configuration)
            for parent_key, child_key in in_spec.items()
        )
    return True


def condition_match(
    transition: Transition,
    context: dict | None = None,
    event: Event | None = None,
    configuration: AbstractSet[StateNode] | None = None,
) -> bool:
    cond = transition.cond
    params = None
    if isinstance(cond, GuardReference):
        params = cond.params
        if callable(params):
            params = _invoke(params, context, event)
        cond_name = cond.name
        guards = getattr(transition.source.machine, "guards", {}) or {}
        if cond_name not in guards:
            raise UnregisteredImplementationError(
                f"Guard '{cond_name}' is referenced by a transition on "
                f"'#{transition.source.id}' at {cond.path or '<unknown>'} but is "
                "not implemented. Pass it via Machine(config, guards={...})."
            )
        cond = guards[cond_name]
    elif isinstance(cond, str):
        guards = getattr(transition.source.machine, "guards", {}) or {}
        if cond not in guards:
            raise UnregisteredImplementationError(
                f"Guard '{cond}' is referenced by a transition on "
                f"'#{transition.source.id}' but is not implemented. "
                f"Pass it via Machine(config, guards={{'{cond}': ...}})."
            )
        cond = guards[cond]

    if cond is not None:
        from xstate.guards import _ComposableGuard  # lazy — avoids circular import
        from xstate.handlers import HandlerAdapter  # lazy — avoids circular import

        # Unwrap HandlerAdapter to check if the inner callable is a _ComposableGuard
        inner = cond.fn if isinstance(cond, HandlerAdapter) else cond
        if isinstance(inner, _ComposableGuard):
            guards = getattr(transition.source.machine, "guards", {}) or {}
            if not inner._call(context, event, guards, configuration):
                return False
        elif not bool(invoke_handler(cond, context, event, params=params)):
            return False

    in_spec = getattr(transition, "in_state", None)
    if in_spec is not None and configuration is not None:
        return _matches_in_state(in_spec, configuration)

    return True


def select_transitions(
    event: Event,
    configuration: AbstractSet[StateNode],
    context: dict | None = None,
    history_value: ReadOnlyHistoryValue | None = None,
):
    if history_value is None:
        history_value = {}
    enabled_transitions: set[Transition] = set()
    atomic_states = [s for s in configuration if is_atomic_state(s)]
    for state_node in atomic_states:
        break_loop = False
        for s in [state_node] + get_proper_ancestors(state_node, None):
            if break_loop:
                break
            for t in sorted(s.transitions, key=lambda t: t.order):
                if (
                    t.event
                    and name_match(t.event, event.name)
                    and condition_match(t, context, event, configuration)
                ):
                    enabled_transitions.add(t)
                    break_loop = True
    enabled_transitions = remove_conflicting_transitions(
        enabled_transitions,
        configuration=configuration,
        history_value=history_value,
    )

    return sorted(enabled_transitions, key=lambda t: t.order)


def select_eventless_transitions(
    configuration: set[StateNode],
    context: dict | None = None,
    event: Event | None = None,
    history_value: HistoryValue | None = None,
):
    if history_value is None:
        history_value = {}
    enabled_transitions: set[Transition] = set()
    atomic_states = [s for s in configuration if is_atomic_state(s)]

    # For each atomic state, select the first (innermost, document-order)
    # matching eventless transition, then move on to the next atomic state.
    # `break_loop` stops scanning ancestors of the *current* atomic state once a
    # match is found; it must not stop us from visiting the remaining atomic
    # states (parallel regions each contribute their own eventless transition).
    for state in atomic_states:
        break_loop = False
        for s in [state] + get_proper_ancestors(state, None):
            if break_loop:
                break
            for t in sorted(s.transitions, key=lambda t: t.order):
                if not t.event and condition_match(t, context, event, configuration):
                    enabled_transitions.add(t)
                    break_loop = True
                    break

    enabled_transitions = remove_conflicting_transitions(
        enabled_transitions=enabled_transitions,
        configuration=configuration,
        history_value=history_value,
    )
    return enabled_transitions


def remove_conflicting_transitions(
    enabled_transitions: set[Transition],
    configuration: AbstractSet[StateNode],
    history_value: ReadOnlyHistoryValue,
) -> set[Transition]:
    ordered = sorted(enabled_transitions, key=lambda t: t.order)

    filtered_transitions: set[Transition] = set()
    for t1 in ordered:
        t1_preempted = False
        transitions_to_remove: set[Transition] = set()
        t1_exit_set = compute_exit_set(
            enabled_transitions=[t1],
            configuration=configuration,
            history_value=history_value,
        )
        for t2 in filtered_transitions:
            t2_exit_set = compute_exit_set(
                enabled_transitions=[t2],
                configuration=configuration,
                history_value=history_value,
            )
            intersection = [value for value in t1_exit_set if value in t2_exit_set]

            if intersection:
                if is_descendent(t1.source, t2.source):
                    transitions_to_remove.add(t2)
                else:
                    t1_preempted = True
                    break
        if not t1_preempted:
            for t3 in transitions_to_remove:
                filtered_transitions.remove(t3)
            filtered_transitions.add(t1)

    return filtered_transitions


def main_event_loop(
    configuration: set[StateNode],
    event: Event,
    context: dict | None = None,
    history_value: HistoryValue | None = None,
) -> tuple[set[StateNode], list[Action], Any]:
    states_to_invoke: set[StateNode] = set()
    if history_value is None:
        history_value = {}
    enabled_transitions = select_transitions(
        event=event,
        configuration=configuration,
        context=context,
        history_value=history_value,
    )
    configuration, actions, internal_queue, context = microstep(
        enabled_transitions,
        configuration=configuration,
        states_to_invoke=states_to_invoke,
        history_value=history_value,
        context=context,
        event=event,
    )
    configuration, actions, context = main_event_loop2(
        configuration=configuration,
        actions=actions,
        internal_queue=internal_queue,
        context=context,
        event=event,
        history_value=history_value,
    )

    return (configuration, actions, context)


def main_event_loop2(
    configuration: set[StateNode],
    actions: list[Action],
    internal_queue: deque[Event],
    context: dict | None = None,
    event: Event | None = None,
    history_value: HistoryValue | None = None,
) -> tuple[set[StateNode], list[Action], Any]:
    enabled_transitions = set()
    macrostep_done = False
    if history_value is None:
        history_value = {}

    while not macrostep_done:
        enabled_transitions = select_eventless_transitions(
            configuration=configuration,
            context=context,
            event=event,
            history_value=history_value,
        )

        if not enabled_transitions:
            if not internal_queue:
                macrostep_done = True
            else:
                internal_event = internal_queue.popleft()
                event = internal_event
                enabled_transitions = select_transitions(
                    event=internal_event,
                    configuration=configuration,
                    context=context,
                    history_value=history_value,
                )
        if enabled_transitions:
            # Accumulate — microstep produces a fresh actions list each call, so
            # extend rather than rebind to avoid dropping actions from prior steps.
            configuration, new_actions, internal_queue, context = microstep(
                enabled_transitions=enabled_transitions,
                configuration=configuration,
                states_to_invoke=set(),  # TODO
                history_value=history_value,
                context=context,
                event=event,
            )
            actions.extend(new_actions)

    return (configuration, actions, context)


def execute_transition_content(
    enabled_transitions: list[Transition],
    actions: list[Action],
    internal_queue: deque[Event],
    context: dict | None = None,
    event: Event | None = None,
) -> Any:
    for transition in enabled_transitions:
        for action in transition.actions:
            context = execute_content(action, actions, internal_queue, context, event)
    return context


def _eval_action_guard(
    guard: Any,
    context: Any,
    event: Event | None,
    guards_registry: dict | None,
) -> bool:
    """Evaluate a ``choose`` branch guard against (context, event).

    Accepts ``None`` (always true), a callable, a registered guard name, or a
    composable guard.  Configuration-dependent guards (``stateIn``) are not
    supported here, so they evaluate against an empty configuration.
    """
    if guard is None:
        return True
    registry = guards_registry or {}
    resolved = guard
    if isinstance(resolved, str):
        resolved = registry.get(resolved)
        if resolved is None:
            raise UnregisteredImplementationError(
                f"choose branch references guard '{guard}' but it is not "
                "implemented. Pass it via Machine(config, guards={...})."
            )
    from xstate.guards import _ComposableGuard
    from xstate.handlers import HandlerAdapter

    inner = resolved.fn if isinstance(resolved, HandlerAdapter) else resolved
    if isinstance(inner, _ComposableGuard):
        return bool(inner._call(context, event, registry, None))
    return bool(invoke_handler(resolved, context, event))


def execute_content(
    action: Action,
    actions: list[Action],
    internal_queue: deque[Event],
    context: dict | None = None,
    event: Event | None = None,
) -> Any:
    if action.type == RAISE_TYPE:
        internal_queue.append(Event(action.data.get("event", "")))
    elif action.type == ASSIGN_TYPE:
        context = _apply_assignment(action, context, event)
    elif action.type == CHOOSE_TYPE:
        guards_registry = action.data.get("_guards", {})
        for branch in action.data.get("branches", []):
            if _eval_action_guard(
                branch.get("guard"), context, event, guards_registry
            ):
                for sub in branch.get("actions", []):
                    context = execute_content(
                        sub, actions, internal_queue, context, event
                    )
                break
    elif action.type == PURE_TYPE:
        fn = action.data.get("fn")
        registry = action.data.get("_actions", {})
        result = invoke_handler(fn, context, event)
        if result is not None:
            specs = result if isinstance(result, list) else [result]
            for spec in specs:
                sub = build_action(spec, registry)
                context = execute_content(
                    sub, actions, internal_queue, context, event
                )
    else:
        actions.append(action)
    return context


def microstep(
    enabled_transitions: list[Transition],
    configuration: set[StateNode],
    states_to_invoke: set[StateNode],
    history_value: HistoryValue,
    context: dict | None = None,
    event: Event | None = None,
) -> tuple[set[StateNode], list[Action], deque[Event], Any]:
    actions: list[Action] = []
    internal_queue: deque[Event] = deque()

    configuration, actions, context = exit_states(
        enabled_transitions,
        configuration=configuration,
        states_to_invoke=states_to_invoke,
        history_value=history_value,
        actions=actions,
        internal_queue=internal_queue,
        context=context,
        event=event,
    )
    context = execute_transition_content(
        enabled_transitions,
        actions=actions,
        internal_queue=internal_queue,
        context=context,
        event=event,
    )

    configuration, actions, internal_queue, context = enter_states(
        enabled_transitions,
        configuration=configuration,
        states_to_invoke=states_to_invoke,
        history_value=history_value,
        actions=actions,
        internal_queue=internal_queue,
        context=context,
        event=event,
    )
    return (configuration, actions, internal_queue, context)


# ===================


def get_configuration_from_state(
    from_node: StateNode,
    state_value: dict | str,
    partial_configuration: set[StateNode],
) -> set[StateNode]:
    if isinstance(state_value, str):
        node = from_node.states.get(state_value)
        assert node is not None, f"State '{state_value}' not found in '#{from_node.id}'"
        partial_configuration.add(node)
    else:
        for key in state_value:
            node = from_node.states.get(key)
            assert node is not None, f"State '{key}' not found in '#{from_node.id}'"
            partial_configuration.add(node)
            get_configuration_from_state(node, state_value[key], partial_configuration)

    return partial_configuration


def get_adj_list(configuration: Iterable[StateNode]) -> dict[str, set[StateNode]]:
    adj_list: dict[str, set[StateNode]] = {}

    for s in configuration:
        if not adj_list.get(s.id):
            adj_list[s.id] = set()

        if s.parent:
            if not adj_list.get(s.parent.id):
                adj_list[s.parent.id] = set()

            adj_list[s.parent.id].add(s)

    return adj_list


def get_state_value(state_node: StateNode, configuration: Iterable[StateNode]) -> Any:
    return get_value_from_adj(state_node, get_adj_list(configuration))


def get_value_from_adj(state_node: StateNode, adj_list: dict[str, set[StateNode]]):
    child_state_nodes = adj_list.get(state_node.id, set())

    if is_compound_state(state_node):
        child_state_node = list(child_state_nodes)[0]

        if child_state_node:
            if is_atomic_state(child_state_node):
                return child_state_node.key
        else:
            return {}

    state_value = {}

    for s in child_state_nodes:
        state_value[s.key] = get_value_from_adj(s, adj_list)

    return state_value

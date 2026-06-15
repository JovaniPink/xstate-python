from __future__ import annotations

import functools
import inspect
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from xstate.action import ASSIGN_TYPE, RAISE_TYPE, Action
from xstate.event import Event
from xstate.state_node import StateNode
from xstate.transition import Transition

HistoryValue = Dict[str, Set[StateNode]]


@functools.lru_cache(maxsize=512)
def _get_params(fn):
    """Return the parameters of *fn*, cached to avoid repeated signature lookups."""
    try:
        return tuple(inspect.signature(fn).parameters.values())
    except (TypeError, ValueError):
        return None


def _invoke(fn, context: Optional[Dict], event: Optional[Event]) -> Any:
    """Call ``fn`` arity-aware, supporting three calling conventions:

    * ``()``                     — zero-arg (SCXML JS conditions)
    * ``(context)``              — positional context only (v4 guard style)
    * ``(context, event)``       — positional context + event (v4 full style)
    * ``(*, context, event)``    — keyword-only (v5 single-object style in Python)

    The v5 JS single-object ``({context, event}) =>`` maps to Python keyword-only
    parameters: ``def guard(*, context, event): ...``
    """
    params = _get_params(fn)
    if params is None:
        return fn(context, event)

    # v5 single-object style: def guard(*, context, event): ...
    kw_only = [p for p in params if p.kind == p.KEYWORD_ONLY]
    if kw_only:
        kw_names = {p.name for p in kw_only}
        kwargs = {}
        if "context" in kw_names:
            kwargs["context"] = context
        if "event" in kw_names:
            kwargs["event"] = event
        return fn(**kwargs)

    if any(p.kind == p.VAR_POSITIONAL for p in params):
        return fn(context, event)

    positional = [
        p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    if len(positional) == 0:
        return fn()
    if len(positional) == 1:
        return fn(context)
    return fn(context, event)


def _apply_assignment(action: Action, context: Optional[Dict], event: Optional[Event]):
    """Mutate ``context`` in place with the updates produced by an assign action."""
    if context is None:
        return
    assignment = action.data.get("assignment", {})
    if callable(assignment):
        updates = _invoke(assignment, context, event) or {}
    else:
        updates = {}
        for key, value in assignment.items():
            updates[key] = _invoke(value, context, event) if callable(value) else value
    context.update(updates)


def compute_entry_set(
    transitions: List[Transition],
    states_to_enter: Set[StateNode],
    states_for_default_entry: Set[StateNode],
    default_history_content: Dict,
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


def add_descendent_states_to_enter(  # noqa: C901
    state: StateNode,
    states_to_enter: Set[StateNode],
    states_for_default_entry: Set[StateNode],
    default_history_content: Dict,
    history_value: HistoryValue,
):
    if is_history_state(state):
        if history_value.get(state.id):
            for s in history_value.get(state.id):
                add_descendent_states_to_enter(
                    s,
                    states_to_enter=states_to_enter,
                    states_for_default_entry=states_for_default_entry,
                    default_history_content=default_history_content,
                    history_value=history_value,
                )
            for s in history_value.get(state.id):
                # Per SCXML the ancestor bound is the history node's parent, not
                # each restored state's parent. For deep history `s` can be a
                # nested atomic descendant, so using `s.parent` would drop the
                # intermediate ancestors between `s` and `state.parent`.
                add_ancestor_states_to_enter(
                    s,
                    ancestor=state.parent,
                    states_to_enter=states_to_enter,
                    states_for_default_entry=states_for_default_entry,
                    default_history_content=default_history_content,
                    history_value=history_value,
                )
        else:
            # No history recorded yet: enter the history state's default target
            # (or, if none is configured, fall back to the parent's initial).
            default_transition = state.transition or state.parent.initial
            default_history_content[state.parent.id] = default_transition
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
                    ancestor=state.parent,
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


def is_descendent(state: StateNode, state2: StateNode) -> bool:
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
    transition: Transition, history_value: HistoryValue
) -> Optional[StateNode]:
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


def find_lcca(state_list: List[StateNode]):
    for anc in get_proper_ancestors(state_list[0], state2=None):
        if all(is_descendent(s, state2=anc) for s in state_list[1:]):
            return anc


def get_effective_target_states(
    transition: Transition, history_value: HistoryValue
) -> Set[StateNode]:
    targets: Set[StateNode] = set()

    for s in transition.target:
        if is_history_state(s):
            if history_value.get(s.id):
                targets.update(history_value.get(s.id))
            else:
                # No recorded history: resolve the default target, falling back
                # to the parent's initial transition when none is configured.
                default_transition = s.transition or s.parent.initial
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
    ancestor: StateNode,
    states_to_enter: Set[StateNode],
    states_for_default_entry: Set[StateNode],
    default_history_content: Dict,
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
    state1: StateNode, state2: Optional[StateNode]
) -> List[StateNode]:
    # Per W3C SCXML getProperAncestors: return the ancestors of state1 in
    # ancestry order, up to *but not including* state2 (state2 is the exclusive
    # upper bound / transition domain). When state2 is None, return all
    # ancestors up to the root.
    ancestors: List[StateNode] = []
    marker = state1.parent
    while marker and marker != state2:
        ancestors.append(marker)
        marker = marker.parent

    return ancestors


def is_final_state(state_node: StateNode) -> bool:
    return state_node.type == "final"


def is_parallel_state(state_node: Optional[StateNode]) -> bool:
    # A null node (e.g. the root's absent parent) is never parallel.
    return state_node is not None and state_node.type == "parallel"


def get_child_states(state_node: StateNode) -> List[StateNode]:
    # Per W3C SCXML, getChildStates returns the real <state>/<parallel>/<final>
    # children and explicitly excludes <history> (and <initial>) pseudo-states.
    # Excluding history here keeps every region-enumeration caller correct: the
    # parallel entry fan-out, is_in_final_state, and the parallel onDone check.
    return [s for s in state_node.states.values() if not is_history_state(s)]


def is_in_final_state(state: StateNode, configuration: Set[StateNode]) -> bool:
    if is_compound_state(state):
        return any(
            is_final_state(s) and (s in configuration)
            for s in get_child_states(state)
        )
    elif is_parallel_state(state):
        return all(is_in_final_state(s, configuration) for s in get_child_states(state))
    else:
        return False


def enter_states(
    enabled_transitions: List[Transition],
    configuration: Set[StateNode],
    states_to_invoke: Set[StateNode],
    history_value: HistoryValue,
    actions: List[Action],
    internal_queue: List[Event],
    context: Optional[Dict] = None,
    event: Optional[Event] = None,
) -> Tuple[Set[StateNode], List[Action], List[Event]]:
    states_to_enter: Set[StateNode] = set()
    states_for_default_entry: Set[StateNode] = set()

    default_history_content = {}

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
            execute_content(
                action,
                actions=actions,
                internal_queue=internal_queue,
                context=context,
                event=event,
            )
        if s in states_for_default_entry:
            # executeContent(s.initial.transition)
            continue
        if default_history_content.get(s.id, None) is not None:
            # executeContent(defaultHistoryContent[s.id])
            continue
        if is_final_state(s):
            parent = s.parent
            grandparent = parent.parent
            donedata = (
                _invoke(s.donedata, context, event)
                if callable(s.donedata)
                else s.donedata
            )
            internal_queue.append(Event(f"done.state.{parent.id}", donedata))

            if is_parallel_state(grandparent):
                if all(
                    is_in_final_state(parent_state, configuration)
                    for parent_state in get_child_states(grandparent)
                ):
                    internal_queue.append(Event(f"done.state.{grandparent.id}"))

    return (configuration, actions, internal_queue)


def exit_states(
    enabled_transitions: List[Transition],
    configuration: Set[StateNode],
    states_to_invoke: Set[StateNode],
    history_value: HistoryValue,
    actions: List[Action],
    internal_queue: List[Event],
    context: Optional[Dict] = None,
    event: Optional[Event] = None,
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
            execute_content(
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
    )


def compute_exit_set(
    enabled_transitions: List[Transition],
    configuration: Set[StateNode],
    history_value: HistoryValue,
) -> Set[StateNode]:
    states_to_exit: Set[StateNode] = set()
    for t in enabled_transitions:
        if t.target:
            domain = get_transition_domain(t, history_value=history_value)
            for s in configuration:
                if is_descendent(s, state2=domain):
                    states_to_exit.add(s)

    return states_to_exit


def name_match(event: str, specific_event: str) -> bool:
    return event == specific_event


def _matches_in_state(in_spec, configuration: Set[StateNode]) -> bool:  # noqa: C901
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
        def _path_active(parts: List[str]) -> bool:
            leaf_key = parts[-1]
            for s in configuration:
                if s.key != leaf_key:
                    continue
                node = s
                matched = True
                for ancestor_key in reversed(parts[:-1]):
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
    context: Optional[Dict] = None,
    event: Optional[Event] = None,
    configuration: Optional[Set[StateNode]] = None,
) -> bool:
    cond = transition.cond
    if isinstance(cond, str):
        guards = getattr(transition.source.machine, "guards", {}) or {}
        if cond not in guards:
            raise ValueError(
                f"Guard '{cond}' is referenced by a transition on "
                f"'#{transition.source.id}' but is not implemented. "
                f"Pass it via Machine(config, guards={{'{cond}': ...}})."
            )
        cond = guards[cond]

    if cond is not None and not bool(_invoke(cond, context, event)):
        return False

    in_spec = getattr(transition, "in_state", None)
    if in_spec is not None and configuration is not None:
        return _matches_in_state(in_spec, configuration)

    return True


def select_transitions(
    event: Event,
    configuration: Set[StateNode],
    context: Optional[Dict] = None,
    history_value: Optional[HistoryValue] = None,
):
    if history_value is None:
        history_value = {}
    enabled_transitions: Set[Transition] = set()
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
    configuration: Set[StateNode],
    context: Optional[Dict] = None,
    event: Optional[Event] = None,
    history_value: Optional[HistoryValue] = None,
):
    if history_value is None:
        history_value = {}
    enabled_transitions: Set[Transition] = set()
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
    enabled_transitions: Set[Transition],
    configuration: Set[StateNode],
    history_value: HistoryValue,
) -> Set[Transition]:
    ordered = sorted(enabled_transitions, key=lambda t: t.order)

    filtered_transitions: Set[Transition] = set()
    for t1 in ordered:
        t1_preempted = False
        transitions_to_remove: Set[Transition] = set()
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
    configuration: Set[StateNode],
    event: Event,
    context: Optional[Dict] = None,
    history_value: Optional[HistoryValue] = None,
) -> Tuple[Set[StateNode], List[Action]]:
    states_to_invoke: Set[StateNode] = set()
    if history_value is None:
        history_value = {}
    enabled_transitions = select_transitions(
        event=event,
        configuration=configuration,
        context=context,
        history_value=history_value,
    )
    configuration, actions, internal_queue = microstep(
        enabled_transitions,
        configuration=configuration,
        states_to_invoke=states_to_invoke,
        history_value=history_value,
        context=context,
        event=event,
    )
    configuration, actions = main_event_loop2(
        configuration=configuration,
        actions=actions,
        internal_queue=internal_queue,
        context=context,
        event=event,
        history_value=history_value,
    )

    return (configuration, actions)


def main_event_loop2(
    configuration: Set[StateNode],
    actions: List[Action],
    internal_queue: List[Event],
    context: Optional[Dict] = None,
    event: Optional[Event] = None,
    history_value: Optional[HistoryValue] = None,
) -> Tuple[Set[StateNode], List[Action]]:
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
                internal_event = internal_queue.pop(0)
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
            configuration, new_actions, internal_queue = microstep(
                enabled_transitions=enabled_transitions,
                configuration=configuration,
                states_to_invoke=set(),  # TODO
                history_value=history_value,
                context=context,
                event=event,
            )
            actions.extend(new_actions)

    return (configuration, actions)


def execute_transition_content(
    enabled_transitions: List[Transition],
    actions: List[Action],
    internal_queue: List[Event],
    context: Optional[Dict] = None,
    event: Optional[Event] = None,
):
    for transition in enabled_transitions:
        for action in transition.actions:
            execute_content(action, actions, internal_queue, context, event)


def execute_content(
    action: Action,
    actions: List[Action],
    internal_queue: List[Event],
    context: Optional[Dict] = None,
    event: Optional[Event] = None,
):
    if action.type == RAISE_TYPE:
        internal_queue.append(Event(action.data.get("event")))
    elif action.type == ASSIGN_TYPE:
        _apply_assignment(action, context, event)
    else:
        actions.append(action)


def microstep(
    enabled_transitions: List[Transition],
    configuration: Set[StateNode],
    states_to_invoke: Set[StateNode],
    history_value: HistoryValue,
    context: Optional[Dict] = None,
    event: Optional[Event] = None,
) -> Tuple[Set[StateNode], List[Action], List[Event]]:
    actions: List[Action] = []
    internal_queue: List[Event] = []

    exit_states(
        enabled_transitions,
        configuration=configuration,
        states_to_invoke=states_to_invoke,
        history_value=history_value,
        actions=actions,
        internal_queue=internal_queue,
        context=context,
        event=event,
    )
    execute_transition_content(
        enabled_transitions,
        actions=actions,
        internal_queue=internal_queue,
        context=context,
        event=event,
    )

    enter_states(
        enabled_transitions,
        configuration=configuration,
        states_to_invoke=states_to_invoke,
        history_value=history_value,
        actions=actions,
        internal_queue=internal_queue,
        context=context,
        event=event,
    )
    return (configuration, actions, internal_queue)


# ===================


def get_configuration_from_state(
    from_node: StateNode,
    state_value: Union[Dict, str],
    partial_configuration: Set[StateNode],
) -> Set[StateNode]:
    if isinstance(state_value, str):
        partial_configuration.add(from_node.states.get(state_value))
    else:
        for key in state_value.keys():
            node = from_node.states.get(key)
            partial_configuration.add(node)
            get_configuration_from_state(
                node, state_value.get(key), partial_configuration
            )

    return partial_configuration


def get_adj_list(configuration: Set[StateNode]) -> Dict[str, Set[StateNode]]:
    adj_list: Dict[str, Set[StateNode]] = {}

    for s in configuration:
        if not adj_list.get(s.id):
            adj_list[s.id] = set()

        if s.parent:
            if not adj_list.get(s.parent.id):
                adj_list[s.parent.id] = set()

            adj_list.get(s.parent.id).add(s)

    return adj_list


def get_state_value(state_node: StateNode, configuration: Set[StateNode]):
    return get_value_from_adj(state_node, get_adj_list(configuration))


def get_value_from_adj(state_node: StateNode, adj_list: Dict[str, Set[StateNode]]):
    child_state_nodes = adj_list.get(state_node.id)

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

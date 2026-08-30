"""Snapshot serialization and deserialization (0.6.0).

Persist a :class:`~xstate.state.State` (MachineSnapshot) to a plain dict
and restore it so a machine can resume from a saved checkpoint.

Serialization format (JSON-compatible, assuming context/output are serializable)::

    {
        "value":         "idle",      # str or nested dict
        "context":       {"count": 0},
        "status":        "active",    # "active" | "done" | "error"
        "history_value": {"#hist": ["child_id"]},
        "output":        null,
        "error":         null,
    }

Usage::

    from xstate import create_actor, Machine
    from xstate.snapshot import deserialize_snapshot, serialize_snapshot

    machine = Machine(config)
    actor   = create_actor(machine).start()
    actor.send("TOGGLE")

    data   = serialize_snapshot(actor.get_snapshot())
    actor2 = create_actor(machine, snapshot=deserialize_snapshot(machine, data)).start()
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from xstate.machine import Machine
    from xstate.state import State


def serialize_snapshot[ContextT, EventDataT, OutputT](
    snapshot: State[ContextT, EventDataT, OutputT],
    *,
    context_serializer: Callable[[ContextT], Any] | None = None,
) -> dict[str, Any]:
    """Serialize *snapshot* to an independent JSON-compatible dictionary.

    ``context_serializer`` converts custom context values, such as dataclasses,
    before the result is copied into the returned payload.
    """
    history_value: dict[str, list[str]] = {}
    for hist_node_id, state_nodes in (snapshot.history_value or {}).items():
        history_value[hist_node_id] = sorted(node.id for node in state_nodes)

    error = snapshot.error
    serialized_context = (
        context_serializer(snapshot.context)
        if context_serializer is not None
        else snapshot.context
    )
    return {
        "value": copy.deepcopy(snapshot.value),
        "context": copy.deepcopy(serialized_context),
        "status": snapshot.status,
        "history_value": history_value,
        "output": copy.deepcopy(snapshot.output),
        "error": repr(error) if error is not None else None,
    }


def deserialize_snapshot[ContextT, EventDataT, OutputT](
    machine: Machine[ContextT, EventDataT, OutputT],
    data: dict[str, Any],
    *,
    context_deserializer: Callable[[Any], ContextT] | None = None,
) -> State[ContextT, EventDataT, OutputT]:
    """Reconstruct a :class:`~xstate.state.State` from a serialized dict.

    Pass the returned state to ``create_actor(machine, snapshot=...)`` or
    ``actor.start(initial_state=...)`` to resume execution.
    ``context_deserializer`` reconstructs a custom context value before the
    machine's context adapter applies its snapshot policy.
    """
    from xstate.state import State

    configuration = set(machine._get_configuration(data["value"]))

    history_value: dict[str, set[Any]] = {}
    for hist_node_id, node_ids in (data.get("history_value") or {}).items():
        nodes = {machine._id_map[nid] for nid in node_ids if nid in machine._id_map}
        if nodes:
            history_value[hist_node_id] = nodes

    raw_context = data.get("context")
    if context_deserializer is not None:
        context = context_deserializer(raw_context)
    else:
        context = cast(ContextT, raw_context if raw_context is not None else {})
    state = State[ContextT, EventDataT, OutputT](
        configuration=configuration,
        context=machine.context_adapter.snapshot(context),
        history_value=history_value,
    )
    if data.get("status") == "error":
        state.status = "error"
        state.error = data.get("error")

    return state

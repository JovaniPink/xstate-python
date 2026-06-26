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

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from xstate.machine import Machine
    from xstate.state import State


def serialize_snapshot(snapshot: State) -> dict[str, Any]:
    """Serialize *snapshot* to a JSON-compatible dict."""
    history_value: dict[str, list[str]] = {}
    for hist_node_id, state_nodes in (snapshot.history_value or {}).items():
        history_value[hist_node_id] = sorted(node.id for node in state_nodes)

    error = snapshot.error
    return {
        "value": snapshot.value,
        "context": snapshot.context,
        "status": snapshot.status,
        "history_value": history_value,
        "output": snapshot.output,
        "error": repr(error) if error is not None else None,
    }


def deserialize_snapshot(machine: Machine, data: dict[str, Any]) -> State:
    """Reconstruct a :class:`~xstate.state.State` from a serialized dict.

    Pass the returned state to ``create_actor(machine, snapshot=...)`` or
    ``actor.start(initial_state=...)`` to resume execution.
    """
    from xstate.state import State

    configuration = set(machine._get_configuration(data["value"]))

    history_value: dict[str, set[Any]] = {}
    for hist_node_id, node_ids in (data.get("history_value") or {}).items():
        nodes = {machine._id_map[nid] for nid in node_ids if nid in machine._id_map}
        if nodes:
            history_value[hist_node_id] = nodes

    state = State(
        configuration=configuration,
        context=dict(data.get("context") or {}),
        history_value=history_value,
    )
    if data.get("status") == "error":
        state.status = "error"
        state.error = data.get("error")

    return state

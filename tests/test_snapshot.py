"""Tests for snapshot serialization / deserialization (0.6.0).

Covers:
  - serialize_snapshot produces a JSON-compatible dict
  - deserialize_snapshot restores value, context, history_value
  - Round-trip: serialize → deserialize → actor continues execution
  - create_actor(machine, snapshot=...) convenience form
  - Error-status snapshots round-trip
"""


from xstate import Machine, create_actor, deserialize_snapshot, serialize_snapshot


def _toggle_machine():
    return Machine(
        {
            "id": "toggle",
            "initial": "inactive",
            "states": {
                "inactive": {"on": {"TOGGLE": "active"}},
                "active": {"on": {"TOGGLE": "inactive"}},
            },
        }
    )


def _counter_machine():
    from xstate import assign

    return Machine(
        {
            "id": "counter",
            "initial": "running",
            "context": {"count": 0},
            "states": {
                "running": {
                    "on": {
                        "INC": {
                            "actions": [assign(lambda c, e: {"count": c["count"] + 1})],
                        }
                    }
                },
            },
        }
    )


# ---------------------------------------------------------------------------
# serialize_snapshot
# ---------------------------------------------------------------------------


def test_serialize_active_snapshot_has_required_keys():
    actor = create_actor(_toggle_machine()).start()
    data = serialize_snapshot(actor.get_snapshot())
    assert set(data.keys()) == {
        "value", "context", "status", "history_value", "output", "error"
    }


def test_serialize_value():
    actor = create_actor(_toggle_machine()).start()
    assert serialize_snapshot(actor.get_snapshot())["value"] == "inactive"


def test_serialize_after_transition():
    actor = create_actor(_toggle_machine()).start()
    actor.send("TOGGLE")
    data = serialize_snapshot(actor.get_snapshot())
    assert data["value"] == "active"
    assert data["status"] == "active"


def test_serialize_context():
    actor = create_actor(_counter_machine()).start()
    actor.send("INC")
    actor.send("INC")
    data = serialize_snapshot(actor.get_snapshot())
    assert data["context"] == {"count": 2}


def test_serialize_error_is_none_for_active():
    actor = create_actor(_toggle_machine()).start()
    data = serialize_snapshot(actor.get_snapshot())
    assert data["error"] is None


def test_serialize_produces_json_compatible_types():
    import json

    actor = create_actor(_counter_machine()).start()
    actor.send("INC")
    data = serialize_snapshot(actor.get_snapshot())
    # Should not raise
    json.dumps(data)


# ---------------------------------------------------------------------------
# deserialize_snapshot
# ---------------------------------------------------------------------------


def test_deserialize_restores_value():
    machine = _toggle_machine()
    actor = create_actor(machine).start()
    actor.send("TOGGLE")

    data = serialize_snapshot(actor.get_snapshot())
    state = deserialize_snapshot(machine, data)
    assert state.value == "active"


def test_deserialize_restores_context():
    machine = _counter_machine()
    actor = create_actor(machine).start()
    actor.send("INC")
    actor.send("INC")
    actor.send("INC")

    data = serialize_snapshot(actor.get_snapshot())
    state = deserialize_snapshot(machine, data)
    assert state.context == {"count": 3}


# ---------------------------------------------------------------------------
# Round-trip: serialize → deserialize → continue
# ---------------------------------------------------------------------------


def test_round_trip_toggle():
    machine = _toggle_machine()
    actor1 = create_actor(machine).start()
    actor1.send("TOGGLE")
    assert actor1.get_snapshot().value == "active"

    data = serialize_snapshot(actor1.get_snapshot())
    restored = deserialize_snapshot(machine, data)

    actor2 = create_actor(machine, snapshot=restored).start()
    assert actor2.get_snapshot().value == "active"
    actor2.send("TOGGLE")
    assert actor2.get_snapshot().value == "inactive"


def test_round_trip_preserves_context():
    machine = _counter_machine()
    actor1 = create_actor(machine).start()
    for _ in range(5):
        actor1.send("INC")

    data = serialize_snapshot(actor1.get_snapshot())
    restored = deserialize_snapshot(machine, data)
    actor2 = create_actor(machine, snapshot=restored).start()
    assert actor2.get_snapshot().context == {"count": 5}
    actor2.send("INC")
    assert actor2.get_snapshot().context == {"count": 6}


# ---------------------------------------------------------------------------
# create_actor(machine, snapshot=...) convenience
# ---------------------------------------------------------------------------


def test_create_actor_with_snapshot_kwarg():
    machine = _toggle_machine()
    actor1 = create_actor(machine).start()
    actor1.send("TOGGLE")

    data = serialize_snapshot(actor1.get_snapshot())
    restored = deserialize_snapshot(machine, data)

    actor2 = create_actor(machine, snapshot=restored).start()
    assert actor2.get_snapshot().value == "active"


def test_snapshot_kwarg_none_uses_initial():
    machine = _toggle_machine()
    actor = create_actor(machine, snapshot=None).start()
    assert actor.get_snapshot().value == "inactive"


# ---------------------------------------------------------------------------
# History state round-trip
# ---------------------------------------------------------------------------


def test_round_trip_with_history():
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "states": {
                "a": {
                    "initial": "a1",
                    "states": {
                        "a1": {"on": {"NEXT": "a2"}},
                        "a2": {},
                        "hist": {"type": "history", "id": "a_hist"},
                    },
                    "on": {"BACK": "b"},
                },
                "b": {"on": {"RESUME": "#a_hist"}},
            },
        }
    )
    actor1 = create_actor(machine).start()
    actor1.send("NEXT")
    assert actor1.get_snapshot().value == {"a": "a2"}
    actor1.send("BACK")
    assert actor1.get_snapshot().value == "b"

    data = serialize_snapshot(actor1.get_snapshot())
    restored = deserialize_snapshot(machine, data)
    actor2 = create_actor(machine, snapshot=restored).start()
    assert actor2.get_snapshot().value == "b"

    actor2.send("RESUME")
    assert actor2.get_snapshot().value == {"a": "a2"}

# Snapshot Persistence

Snapshots can be serialized to plain data and restored against the same
machine. This supports checkpoints, process handoff, and replay from an
application-owned store.

## Serialize And Restore

```python
import json

from xstate import (
    create_actor,
    deserialize_snapshot,
    serialize_snapshot,
)

actor = create_actor(machine).start()
actor.send("ADVANCE")

payload = json.dumps(serialize_snapshot(actor.get_snapshot()))
actor.stop()

restored = deserialize_snapshot(machine, json.loads(payload))
resumed = create_actor(machine, snapshot=restored).start()
```

The serialized dictionary contains:

| Field | Meaning |
|---|---|
| `value` | String or nested state value |
| `context` | Application context |
| `status` | `active`, `done`, or `error` |
| `history_value` | Recorded history-state configuration by node ID |
| `output` | Snapshot output when JSON-compatible |
| `error` | `repr(error)` for an error snapshot |

Context and output must already be JSON-compatible if the payload is sent
through `json.dumps()`.

## Compatibility Boundary

Restore only into the same machine definition, or a definition whose active
state IDs and hierarchy are intentionally compatible. Deserialization resolves
state and history IDs through that machine's parsed state tree. It is not a
general migration engine and does not validate arbitrary untrusted payloads.

For a changed machine, migrate the stored dictionary in application code before
calling `deserialize_snapshot()` and test that migration against representative
checkpoints.

## What Is Reconstructed

The active configuration, context, and known history nodes are reconstructed.
Snapshot status and output are derived again from the restored configuration;
the serialized `output` field is descriptive rather than assigned independently.
An error status is restored, with the serialized error representation exposed
as text.

The restored public snapshot keeps the normal immutable boundary:
configuration is a `frozenset`, actions are a tuple, and history values are
read-only.

## What Is Not Persisted

Serialization does not capture:

- pending `after` deadlines or delayed-send remaining time;
- running invoked or spawned child actor internals;
- subscriptions;
- queued events;
- the last event object or pending side-effect actions.

Starting an actor from an active restored state schedules that state's timers
again from their full configured delay. Applications that need wall-clock timer
continuity should persist deadlines separately and send an explicit recovery
event after restore.

Child actors are reconciled from the restored active configuration. Persist
their domain data separately when their internal progress matters.

## Operational Guidance

- Treat snapshots as versioned application data even though the library payload
  does not currently include a schema-version field.
- Store the application and machine version alongside each payload.
- Validate context before restore when it came from outside a trusted store.
- Stop the old actor before starting the restored actor to avoid duplicate
  timers, invoked work, or side effects.

See [snapshot resume](../examples/snapshot_resume.py) for a JSON round-trip that
continues processing on a new actor.

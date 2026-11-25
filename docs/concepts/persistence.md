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

The returned dictionary owns independent copies of the snapshot value, context,
and output. Mutating the serialized payload does not mutate the live snapshot.

Use the optional context codec callbacks when an application context is not
directly JSON-compatible. For example, an immutable dataclass context can be
encoded and restored explicitly:

```python
from dataclasses import asdict

data = serialize_snapshot(snapshot, context_serializer=asdict)
restored = deserialize_snapshot(
    machine,
    data,
    context_deserializer=lambda value: AppContext(**value),
)
```

Without a codec, the deserializer passes the stored context through the
machine's configured `ContextAdapter`. A codec is the application boundary for
validating and reconstructing custom context types.

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
The configuration determines whether the snapshot is active or completed. An
error status is restored, with the serialized error representation exposed as
text; the original exception object is not recreated.

For a completed configuration, a present `output` field is restored as an
independent deep copy. This preserves computed output without calling the
original output function again. Explicit JSON `null` restores `None`, even if
the machine definition has a literal output value. Mutating a stored payload
after restore does not change the restored output, and mutating the restored
output does not change the payload.

Legacy payloads that omit `output` keep the earlier fallback: a literal final
output is read from the compatible machine definition, while a callable final
output yields `None`. Restore never invokes that callable to recover a missing
value. Applications that need completed results should persist the `output`
field emitted by `serialize_snapshot()`. Active configurations always have
`output=None`, even if the payload contains an output value.

Pass the restored snapshot at actor construction to skip fresh chart
initialization as well:

```python
restored = deserialize_snapshot(machine, data)
actor = create_actor(machine, snapshot=restored)
assert actor.get_snapshot() is restored
actor.start()
```

Before `start()`, `get_snapshot()` exposes the supplied snapshot, including its
status, context, and stored output. The actor runtime remains `"not_started"`.
Construction does not evaluate the machine's initial assignments, guards, or
output functions; it does not notify inspectors or subscribers, schedule timers,
or start invoked children. On startup, an inspector receives the existing
`xstate.init` notification with the restored snapshot and no computed microsteps.
Restored active resources follow the normal startup policy described below.

An explicit `actor.start(initial_state=other_snapshot)` still overrides the
constructor snapshot. Creating an actor without `snapshot=`, or a standalone
interpreter, retains eager initial-state computation. Supplying a snapshot only
later through `start(initial_state=...)` cannot undo assignments, guards, or
output evaluation that already occurred during construction. Skipping fresh
chart initialization does not bypass machine construction, context codecs, or
the configured `ContextAdapter` used to prepare the supplied snapshot.

`deserialize_snapshot()` produces a state without pending actions. Passing a
raw `State` that still contains actions preserves the existing startup behavior:
those actions execute when the actor starts. Construction does not strip them
or turn a transition result into an effect-free checkpoint.

The restored public snapshot keeps the normal immutable boundary:
configuration is a `frozenset`, actions are a tuple, and history values are
read-only. This does not make context or output dictionaries recursively
read-only. Live context follows the configured `ContextAdapter` policy;
serialization provides a detached copy for storage or observation.

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

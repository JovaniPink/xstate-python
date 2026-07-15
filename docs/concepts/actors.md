# Actors

Actors own running logic. A machine describes transitions; an actor gives that
machine an identity, current snapshot, mailbox-like `send()` boundary, and
lifecycle.

## Machine Actors

Create and start an actor from any `Machine`:

```python
from xstate import Machine, create_actor

machine = Machine(config)
actor = create_actor(machine).start()

actor.send("START")
snapshot = actor.get_snapshot()

actor.stop()
```

`start()` is idempotent while the actor is running. `send()` processes an event
through the machine's run-to-completion queue. Events sent before start or after
stop are dropped by the machine runtime.

Subscribe when another part of the application needs snapshot notifications:

```python
subscription = actor.subscribe(lambda snapshot: print(snapshot.value))
subscription.unsubscribe()
```

The actor owns its interpreter and timers. Call `stop()` when its lifecycle is
not already owned by a parent actor.

## Invoked Actors

An `invoke` declaration starts child logic while its state is active:

```python
machine = Machine(
    {
        "id": "loader",
        "initial": "loading",
        "states": {
            "loading": {
                "invoke": {
                    "id": "loadUser",
                    "src": "loadUser",
                    "input": lambda context, _event: {
                        "user_id": context["user_id"]
                    },
                    "onDone": "success",
                    "onError": "failure",
                }
            },
            "success": {"type": "final"},
            "failure": {},
        },
    },
    actors={"loadUser": load_user_logic},
)
```

The child is reconciled with the active configuration. Entering the invoking
state starts it; leaving that state stops it. Completion produces
`done.invoke.<id>`, failure produces `error.platform.<id>`, and snapshot-capable
logic can produce `snapshot.invoke.<id>`.

## Actor Logic Helpers

| Helper | Wraps |
|---|---|
| `from_promise(fn)` | A value-returning or awaitable function |
| `from_callback(fn)` | Callback logic that may receive events and return cleanup |
| `from_observable(source)` | An observable or async iterable snapshot source |
| `to_promise(actor)` | Actor completion as an awaitable result |

Promise input is resolved from `invoke.input` before the child starts. A
resolved value completes the actor; an exception moves its snapshot to error
and drives the parent's `onError` transition.

See [fetch with retry](../examples/fetch_with_retry.py) for invoked promise
logic, context assignment, guarded retry, and deterministic backoff.

## Actor Trees And Messaging

Machine actors can spawn children into the same `ActorSystem`. Use
`send_parent(event)` for child-to-parent communication and
`send_to(actor_id, event)` for a known actor in that system. These are
interpreter-owned actions: the runtime routes them after the machine computes
the next snapshot.

Actor IDs must be unique within a system. A parent owns the lifetime of its
spawned and invoked children; stopping the parent stops those children as well.

## Choosing An Actor Boundary

Use `interpret(machine)` for a standalone synchronous service. Use
`create_actor(machine)` when identity, parent/child ownership, invocation, or
actor messaging is part of the design. Both preserve the same machine
configuration and transition semantics.

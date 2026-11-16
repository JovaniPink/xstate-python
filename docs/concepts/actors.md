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
stop or completion are dropped by the machine runtime. A stopped or completed
machine actor does not restart.

Subscribe when another part of the application needs snapshot notifications:

```python
subscription = actor.subscribe(lambda snapshot: print(snapshot.value))
subscription.unsubscribe()
```

The actor owns its interpreter and timers. Call `stop()` when its lifecycle is
not already owned by a parent actor.

Consumers that only send, read, and subscribe can depend on the structural
`ActorRef[SendEventT, SnapshotT]` protocol. Concrete `Actor` values still own
`start()`, `stop()`, and `spawn()`:

```python
from xstate import ActorRef, State


def observe(ref: ActorRef[str, State]) -> None:
    ref.subscribe(lambda snapshot: print(snapshot.value))
    ref.send("START")
```

`ActorSystem.get()`, public parent references, and public child mappings return
widened `ActorRef[Any, Any]` values because an actor system can contain
heterogeneous logic. `create_actor()` and `spawn()` still return precise
concrete `Actor` types when their logic is known.

### Machine Completion

A machine actor that reaches a final snapshot reports runtime status `"done"`.
It releases its timers, stops all owned children, including root invocations and
manually spawned actors, and unregisters from the actor system before the final
notification. Its final snapshot and output remain readable. Explicit `stop()`
reports `"stopped"`; calling it after completion keeps the final snapshot and
output. Neither lifecycle outcome permits restart.

Terminal effects run before cleanup. If one raises, cleanup still runs and the
committed final snapshot is preserved while the action exception propagates;
later effects and the final notification are skipped. See
[runtime completion](runtimes.md#final-completion).

If a child cleanup raises during parent completion or explicit stop, teardown
still attempts the remaining children, clears ownership, and unregisters the
actors. Cleanup-only failure propagates the first cleanup exception; an action
failure remains primary if both fail. A callback's cleanup is consumed even
when it raises, so repeating `stop()` does not run it again.

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

The child is reconciled after the macrostep's actions and before public snapshot
notifications. Retaining its owning state keeps the child. Exiting that state
stops it; exiting and re-entering replaces it even when the final configuration
looks unchanged. A state entered and left within one macrostep does not start
its transient invocation. Completion produces
`done.invoke.<id>`, failure produces `error.platform.<id>`, and snapshot-capable
logic can produce `snapshot.invoke.<id>`.

Ordinary `invoke.input` expressions read the committed snapshot's context and
outer event. They do not use an entry action's captured arguments. JavaScript
child-startup and entry-effect ordering can differ; the checked lifecycle cases
do not establish general ordering or invocation-input parity.

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

A promise function can receive its input through an ordinary positional
parameter with any name, such as `def fetch(user_id): ...`. No-argument
functions and handlers using keyword-only `input` or `**kwargs` also work.
Optional and variadic positional parameters now receive actor input, even when
the function also accepts `**kwargs`; previously they could keep their default
or receive no positional arguments. Wrap a function in a zero-argument callable
when its own default should be used instead. An explicitly named `input`
parameter keeps its existing keyword binding when that satisfies the function
signature. A `**kwargs`-only handler still receives `input` as a keyword.
When a callable's signature cannot be inspected, as with some built-ins, input
is passed positionally. Wrap an uninspectable zero-argument or keyword-only
callable in a Python function to make its intended signature visible.

`to_promise()` accepts concrete actors and structural actor references whose
snapshots satisfy `CompletionSnapshot[OutputT]`. Output inference remains
precise for both forms.

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
Completing a machine parent also stops its children. Calling `spawn()` after
the parent has stopped or completed returns a stopped child and does not leave
that child registered in the actor system.

For a callback child, messages admitted before it stops remain valid queued
events, including messages sent by its cleanup while the parent is still
active. A later call through the old child's `send_back` is ignored after that
child has stopped. Completion/error emissions from a replaced invocation are
accepted only from the current child instance; events already queued are not
filtered again when dequeued. Parent completion still discards its pending work.

Python removes a completed machine actor's children from its child registry.
XState can retain stopped root-invocation references in its completed snapshot.
The [comparison contract](xstate-compatibility.md#re-entry-and-completion)
records this representation difference separately from the matching cleanup.

## Choosing An Actor Boundary

Use `interpret(machine)` for a standalone synchronous service. Use
`create_actor(machine)` when identity, parent/child ownership, invocation, or
actor messaging is part of the design. Both preserve the same machine
configuration and transition semantics.

Machine-backed actors execute machine actions synchronously; they do not await
action results. An invoked promise or observable can still run asynchronously
when its starting thread has a running event loop. `interpret_async` awaits
machine actions but does not start invoked actors or route actor messages. See the
[runtime capability matrix](runtimes.md) for the warnings and tradeoffs.

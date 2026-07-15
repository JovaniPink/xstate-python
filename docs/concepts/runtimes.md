# Runtime Choices

The same `Machine` can be used through four runtime boundaries. Choose the
smallest one that owns the behavior your application needs.

| Boundary | Choose it when |
|---|---|
| `Machine.transition` | You want pure `(snapshot, event) -> snapshot` evaluation |
| `interpret(machine)` | You need sync action execution, subscriptions, queues, or timers |
| `interpret_async(machine)` | Actions are awaitable or events are coordinated by asyncio |
| `create_actor(machine)` | The machine participates in an actor tree or invokes child logic |

## Synchronous Interpreter

The synchronous interpreter owns the current snapshot and executes actions:

```python
from xstate import interpret

service = interpret(machine).start()
subscription = service.subscribe(lambda snapshot: print(snapshot.value))

service.send("SUBMIT")

subscription.unsubscribe()
service.stop()
```

Calls to `send()` are serialized. An event sent while another event is being
processed is queued until the active macrostep completes. This preserves
run-to-completion even when an action sends another event.

The default `ThreadClock` schedules real timers. Tests and deterministic tools
should inject `SimulatedClock` and advance it explicitly:

```python
from xstate import SimulatedClock, interpret

clock = SimulatedClock()
service = interpret(machine, clock=clock).start()
clock.increment(1_000)
```

Stopping an interpreter cancels its active `after` timers and delayed sends,
clears listeners, and drops later events.

## Async Interpreter

The async interpreter provides awaitable lifecycle and send operations:

```python
from xstate import interpret_async

service = interpret_async(machine)
await service.start()
snapshot = await service.send({"type": "SUBMIT", "request_id": 7})
await service.stop()
```

Actions that return awaitables are executed in declaration order and awaited
before that event's `send()` completes. Concurrent callers receive completion
for their own queued event. Subscribers remain synchronous observers; launch
async work from actions rather than subscription callbacks.

Async `after` transitions use the running event loop. The pure transition and
guard layer remains synchronous.

See [async workflow](../examples/async_workflow.py) for a complete program.

## Actors

`create_actor(machine)` wraps a machine with an XState v5-style actor API. It is
the right boundary for parent/child relationships, `invoke`, spawning,
`send_parent`, and `send_to`. Machine actors use the synchronous interpreter
internally; promise and observable actor logic can settle asynchronously.

Actor and persistence behavior is documented in dedicated concept guides.

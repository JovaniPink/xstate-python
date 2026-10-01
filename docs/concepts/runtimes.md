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

Initialization owns the same queue boundary. Entry actions and the initial
notification finish before events sent by startup actions, inspectors,
subscribers, or timers are drained in FIFO order. A sync `send()` that queues
during processing returns the currently committed snapshot immediately; its
return does not mean that the queued event has completed. The call that owns
processing drains the queue before it returns.

Callbacks run outside the synchronous mutation lock. `stop()` cancels queued
work and prevents later actions and notifications; it does not interrupt an
action already executing.

The default `ThreadClock` schedules all timers for one clock on a single
on-demand daemon worker. The worker exits after the last timer fires or is
canceled. Tests and deterministic tools should inject `SimulatedClock` and
advance it explicitly:

```python
from xstate import SimulatedClock, interpret

clock = SimulatedClock()
service = interpret(machine, clock=clock).start()
clock.increment(1_000)
```

Stopping an interpreter cancels its active `after` timers and delayed sends,
clears listeners, and drops later events. A stopped interpreter does not
restart; create a new interpreter to run the machine again.

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

This completion rule also applies during startup. A same-task reentrant
`await send()` returns the current snapshot after enqueueing, so the active
action can return and let the queue drain. Another task awaits completion of
its own event. Do not await a separately created send task from the action
that owns processing: that task is waiting for the action to finish.

If startup fails or its task is cancelled, queued callers receive the same
failure or cancellation, queued work is discarded, and processing ownership
is released. Committed snapshots and lifecycle status remain in place unless
`stop()` changed the status. Normal processing cancellation likewise settles
queued callers. Stopping resolves dropped async sends with the current
snapshot; that resolution does not imply their events were processed.

Async `after` transitions use the running event loop. The pure transition and
guard layer remains synchronous.

`await service.stop()` cancels and waits for interpreter-owned timer tasks to
settle before returning. An action that is already awaiting may finish in its
caller's send task, but later runtime actions from that macrostep are skipped.
The interpreter does not wait for application tasks created outside it.

See [async workflow](../examples/async_workflow.py) for a complete program.

## Action Failure And External Completion

Both runtimes install a computed snapshot before executing its side-effect
actions. If an action raises, the exception propagates, the destination
snapshot remains committed, and later actions and the notification are
skipped. Remaining queued work is discarded. Assignments computed as part of
the transition also remain committed. Neither chart state nor external
mutations receive transactional rollback.

For example, a `TICK` can select `scanning`, then its staging drive command can
fail. The [controller example](../examples/docking_controller.py) still exposes
`Phase.SCANNING`; its caller must clean up and handle the command failure.
Inspection frames cannot be treated as acknowledgements from the drive.

When successful external completion determines the next domain state, model
an in-progress state and use invoked actor `onDone` / `onError` transitions.
The [fetch-with-retry example](../examples/fetch_with_retry.py) demonstrates
this pattern with `from_promise`; see also [XState invoke semantics](https://stately.ai/docs/invoke).

## Bounded Execution And Microstep Traces

Use `max_iterations` to fail before a macrostep executes more enabled
microsteps than the application permits. The same limit can be stored in
portable machine JSON as `options.maxIterations`; a non-`None` constructor
keyword takes precedence.

```python
from xstate import Machine

machine = Machine(config, max_iterations=100)
```

The default is unlimited. Boolean, negative, and non-integer limits raise
`InvalidConfigError`. If a limit is exceeded, `InfiniteLoopError` is raised
before the next microstep runs, and a running interpreter keeps its last
committed snapshot.

Pure trace helpers expose settled intermediate snapshots without exposing the
internal transition queue:

```python
from xstate import get_initial_microsteps, get_microsteps

initial_steps = get_initial_microsteps(machine)
steps = get_microsteps(machine, machine.initial_state, {"type": "SUBMIT"})

for step in steps:
    print(step.event.name, step.snapshot.value, step.transitions)
```

Each intermediate snapshot contains only that microstep's actions. The normal
`Machine.transition` result still contains every macrostep action in execution
order. Ignored events appear with an empty `transitions` tuple.

Normal transitions do not build trace-only context snapshots. Those snapshots
are collected only when a trace helper or interpreter inspector requests them.

Sync and async interpreters accept an `inspect` callback. It receives one
`MacrostepTrace` for initialization and one for each external event after the
settled snapshot is installed but before actions and subscribers run:

```python
from xstate import interpret

service = interpret(machine, inspect=lambda trace: print(trace.snapshot.value))
service.start()
```

Inspector failures emit `RuntimeWarning` and do not interrupt machine behavior.
Machine-backed `create_actor` accepts the same callback. This local callback is
not the remote `@statelyai/inspect` protocol.

The [controller's Markdown recorder](../examples/docking_controller.py) captures
initialization and every recorded microstep, including ignored events. It
formats diagrams with `to_mermaid(machine, snapshot=...)` after execution and
lists selected transitions in order. Several transitions can belong to one
microstep, and several microsteps to one macrostep. It deliberately does not
choose a single edge to represent the entire event. See the
[controller guide](controllers.md) for replay and measurement commands.

## Actors

`create_actor(machine)` wraps a machine with an XState v5-style actor API. It is
the right boundary for parent/child relationships, `invoke`, spawning,
`send_parent`, and `send_to`. Machine actors use the synchronous interpreter
internally; promise and observable actor logic can settle asynchronously.

Actor and persistence behavior is documented in dedicated concept guides.

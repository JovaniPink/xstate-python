# Controllers, Ticks, And Replay

The [docking controller](../examples/docking_controller.py) adapts an ordinary
Python application to the existing interpreter. Its
[JSON chart](../examples/docking_controller.json) owns phase structure,
transition selection, and named timeouts. Explicit action and guard registries
bind controller methods at construction time. Hardware handles, service
clients, and mutable resources stay on the controller object.

`start(DockingGoal(...))` creates a fresh interpreter and sends `START`.
`tick(TickSample(...))` sends a typed `TICK` mapping and returns a `Phase`.
`cancel()` sends `CANCEL`; `close()` stops timers and performs unfinished drive
cleanup, independently of the chart phase. Use `try/finally` around every operation.
After a terminal or closed operation, another `start` creates a fresh
interpreter rather than resetting the previous one. Starting while an
operation is active raises `RuntimeError`.

The `Phase` Enum projects this example's flat string state values. Hierarchical
and parallel charts retain the general snapshot API: use `matches`, tags,
metadata, or an application-specific projection rather than forcing their
values into one Enum.

## What Advances The Controller

The application loop owns sensor sampling and tick cadence. The deterministic
demo uses `SimulatedClock` and fake drive commands; replace these with your
application's resource and scheduling policy when integrating.

| Concept | Meaning |
|---|---|
| `TICK` | An ordinary external event chosen by the application |
| `always` | An eventless transition evaluated until the chart settles |
| Internal microstep | One engine step within a run-to-completion macrostep |
| `after` | A timer-generated event scheduled by the interpreter |

One tick issues one control command for its current normal phase. A staging
sample that selects `scanning` issues the staging command; scanning control
waits for the next tick. Pure guards inspect samples without commanding the
drive. A fault selects `failed` before a control command and runs terminal
cleanup. Each active phase has a fresh named `phaseTimeout` of 1,000 ms in the
demo, removed when that phase exits.

Call `controller.advance_time(milliseconds)` to advance an injected
`SimulatedClock` under the controller boundary; the return is a `Phase`.
Negative or nonfinite values raise `ValueError`; other clock types raise
`RuntimeError`. Zero is permitted. Own the injected clock exclusively and do
not call its scheduling or advancement methods outside the facade.

## Concurrent Callers And Timer Delivery

The controller serializes `start`, `tick`, `cancel`, `close`, and timer delivery
with one reentrant lock, held through actions, inspection, and notification.
Calls admitted from another thread wait for the current operation to finish.
Admission follows lock acquisition, with no caller FIFO guarantee. A facade
call returns its phase after its operation has completed. The runtime's own
queued-send contract remains unchanged.

The private clock adapter takes the controller lock before entering the
interpreter and invalidates cancelled callbacks, including callbacks already
dispatched by the underlying scheduler but waiting for admission. Default
`ThreadClock` timeouts run on its scheduler thread. Controller-issued drive
calls never overlap, but can execute on different threads. A resource that
requires fixed thread ownership needs an application-specific dispatch policy.

Callbacks may read `phase` and the typed `snapshot` property. During admitted
controller work, calling a mutating facade method from a drive, inspection,
or subscriber callback raises
`RuntimeError` before changing state. Callbacks must not wait for another
thread to reenter the controller: that thread is waiting for the callback to
finish. `service` remains available for advanced diagnostics; direct
interpreter mutation bypasses the facade's concurrency guarantees.

An `always` chain may traverse several states during one macrostep. That is
useful for immediate chart decisions, but it is not another periodic poll.
Sending a follow-up event from an action queues it until the current actions
and notification finish, including during initialization. The
[runtime guide](runtimes.md) describes sync return values, async completion,
and reentrant sends.

## Failure And Cleanup

The chart destination is committed before side-effect actions run. A drive
method exception propagates and can leave both the destination snapshot and
earlier external mutations in place. Later actions and notifications are
skipped. `close()` cancels the interpreter's timers and attempts drive cleanup;
it cannot undo external work or interrupt a drive method already executing.
Cleanup is marked pending before `begin`, including when `begin` partially
fails. Only a successful `drive.stop()` clears it. Terminal `halt` and `close`
share this cleanup operation, so a failing final docking command cannot
suppress cleanup merely because the snapshot is `completed`. Repeated
successful closes do not issue another stop. A failed cleanup remains pending
for another close or the next start; start cannot begin another operation
until prior cleanup succeeds. The interpreter is stopped in `finally`, even
when drive cleanup raises.

`close()` and cancellation wait for admitted commands; they cannot forcibly
interrupt a blocked drive method. When startup and its automatic cleanup both
fail, the cleanup exception is raised with the startup exception as its
explicit cause. Simulated-clock callback exceptions propagate from
`advance_time`; real `ThreadClock` callback exceptions follow its existing
traceback reporting behavior. The application must handle command and cleanup
failures. A `completed` observation therefore represents a chart decision,
not independent proof that every external command succeeded.

If external completion should authorize the next domain state, model it with
an invoked actor and `onDone` / `onError`. The
[fetch-with-retry example](../examples/fetch_with_retry.py) provides a complete
promise/invoke pattern.

## Context Policy For Frequent Ticks

The default context adapter deep-copies context for snapshot isolation. Large
lists, resource objects, or mutable caches in context can make every tick
expensive. Start with a small context; keep resources on the controller.

For immutable values, the existing dataclass adapter can reuse context between
snapshots and apply `assign` with `dataclasses.replace`:

```python
from dataclasses import dataclass
from xstate import Machine, dataclass_context

@dataclass(frozen=True)
class Context:
    goal_id: str = ""
    calibration: tuple[int, ...] = ()

config["context"] = Context()
machine = Machine(config, context_adapter=dataclass_context())
```

The adapter relies on the caller's immutability contract. Use immutable fields
throughout; a frozen dataclass containing a mutable list still shares that
list. Public configuration, action, and history containers retain their
existing immutability guarantees regardless of context policy.

## Structural Markdown Replay

From the repository's locked development environment:

```bash
poetry run python docs/examples/docking_controller.py --trace-md /tmp/success.md
poetry run python docs/examples/docking_controller.py --scenario timeout --trace-md /tmp/timeout.md
poetry run python docs/examples/docking_controller.py --scenario cancel --trace-md /tmp/cancel.md
```

Without `--trace-md`, the demo runs without inspection capture. With it, a
bounded recorder retains at most 200 chart-state frames and counts omitted
frames. Formatting happens after execution and cleanup. Each initialization
or microstep frame includes a Mermaid diagram and an ordered transition table
with event, source ID, target IDs, and active states. Ignored events have an
empty transition list, displayed with empty source/target cells. Eventless
transitions are labelled `always`; a frame's heading retains the triggering
event. Parallel selections produce multiple table rows in one frame.

Open the Markdown in a Mermaid-capable consumer, such as GitHub's rendered
Markdown or a Mermaid-enabled editor preview. `[active]` captions identify
the observed configuration; initial arrows always describe the configured
chart. The exporter depicts chart topology and does not claim to encode every
SCXML semantic detail of history or parallel execution.

Frames are observations before side effects complete. The report exports
structural diagnostics only: context and event payload contents are omitted.
Chart identifiers and event names remain visible. The recorder holds snapshot
references in memory, so this output rule is not a data-retention policy for
an application handling sensitive context.

## Reproducible Local Measurements

```bash
poetry run python -m scripts.benchmark_runtime --samples 3000 --warmup 200
poetry run python -m scripts.benchmark_runtime --samples 3000 --json > /tmp/benchmark.json
```

The dependency-free script reports Python implementation/version, platform,
architecture, sample count, median, p95, and p99. Percentiles use nearest rank.
Event workloads time warmed `GO` / `BACK` cycles and divide by two, reporting
microseconds per event-equivalent. They include pure and sync operation with
empty context, a 1,000-integer mutable list under the default adapter, an
immutable dataclass with a 1,000-integer tuple, pure microstep tracing, and
sync inspection with a rolling 200-record deque. A separate
`controller_serialized_tick` workload measures the full untraced facade over
two staging ticks, using a constant-memory counting drive and simulated time
that stays fixed. It includes synchronization, guards, context handling, and
drive dispatch; it does not isolate lock cost or measure contention.
No application I/O is timed.

Capture uses a rolling deque to include retention work for every event.
Formatting uses the actual example recorder and is measured separately over
a 200-frame report, in microseconds per whole report. `--format-samples`
controls the number of report measurements (default 20).
Formatting measures Markdown and Mermaid text generation; Mermaid rendering,
disk writes, and browser work are excluded.

These workloads exercise different semantics. Compare context policies and
trace modes under a controlled workload before optimizing the engine. Report
formatting costs do not describe interpreter latency. Results are local
baselines; CI checks that the script runs and reports the workloads, without
fixed timing thresholds. They do not provide real-time scheduling guarantees.

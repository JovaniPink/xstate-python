# Runnable examples

Start with the [getting-started guide](../getting-started.md) to install this
checkout in a Python 3.13+ virtual environment. Then run the commands below
from the repository root with that environment active. Contributors can use
`poetry run python` in place of `python`.

These are source files in the repository, not commands installed by the wheel.
The default programs use scripted inputs and local fake resources; they need
no model provider, API credentials, or network service. JSON and XML fixtures
are loaded relative to their program, so an absolute script path also works
from another working directory.

## Choose an example

| Start here when you want to… | Program | What to observe |
| --- | --- | --- |
| Use ordinary Python domain types | [Typed context](typed_context.py) | Frozen dataclasses, typed events, named guards, context replacement, final output |
| Model evidence for a software revision | [Revision gate](revision_gate.py) + [JSON](revision_gate.json) | New code invalidates old CI/review evidence; stale results cannot make it ready |
| Invoke work and retry a failure | [Fetch with retry](fetch_with_retry.py) + [JSON](fetch_with_retry.json) | Promise actors, completion/error events, assignments, deterministic backoff |
| Await an action before continuing | [Async workflow](async_workflow.py) | `interpret_async`, subscriptions, per-event completion |
| Restore state and completed output | [Snapshot resume](snapshot_resume.py) | JSON round-trip, pre-start snapshot access, explicit actor ownership |
| Coordinate parallel regions | [Traffic intersection](traffic_intersection.py) + [JSON](traffic_intersection.json) | Hierarchy, parallel states, named delays, guards, simulated time |
| Import a supported SCXML document | [SCXML toggle](scxml_toggle.py) + [XML](scxml_toggle.scxml) | Safe conditions, raised events, pure transitions |
| Wrap a chart in an application controller | [Docking controller](docking_controller.py) + [JSON](docking_controller.json) | Typed methods, resource ownership, cancellation, timeout, structural replay |

Run the complete noninteractive collection:

```bash
python docs/examples/typed_context.py
python docs/examples/revision_gate.py
python docs/examples/fetch_with_retry.py
python docs/examples/async_workflow.py
python docs/examples/snapshot_resume.py
python docs/examples/traffic_intersection.py
python docs/examples/scxml_toggle.py
python docs/examples/docking_controller.py
```

## Typed context: preserve earlier observations

[`typed_context.py`](typed_context.py) models reviewing release notes. An
`APPROVE` event is blocked while findings remain. `RESOLVE` carries a count,
which a guard checks before `assign` replaces the frozen `ReviewContext`.

Expected output:

```text
Before resolution: reviewing; remaining=2
After resolution: original remaining=2; current remaining=0
After approval: done; output=ReviewResult(title='Release notes', approved=True)
```

Look at `build_machine()` and the named functions passed to `setup()`. The
context adapter reuses immutable values, so every field must follow that
contract: a frozen dataclass containing a list still shares a mutable list.
Type annotations help a static checker; they do not validate arbitrary input
at runtime. See [static typing](../concepts/typing.md).

## Revision gate: keep evidence attached to the code

[`revision_gate.py`](revision_gate.py) loads a shared data-only JSON definition
and binds named Python guards and assignments. It records CI and review results
for one current head SHA. A new revision clears both results; stale results
leave the current evidence unchanged. Readiness remains revocable when a
current CI rerun fails or a review requests changes.

The script first reaches `ready` for revision A, moves to `collecting` for
revision B, ignores old A results, and resumes B from a JSON checkpoint. It then
shows approval and a failed/successful CI rerun. Follow the
[complete walkthrough](../guides/revision-gate.md) for exact output, the event
contract, and the state diagram.

This is a recorded-input policy example. It does not authenticate events,
execute models, merge a PR, or write a crash-safe checkpoint. A host must
establish external authority and event ordering before sending events. The
new chart is not part of the pinned Python/JavaScript comparison corpus.

## Fetch with retry: use actor lifecycle events

[`fetch_with_retry.py`](fetch_with_retry.py) invokes a synthetic promise actor
that fails twice and then succeeds. Named handlers record errors and attempts,
while `after` schedules retries through `SimulatedClock` without waiting for
wall-clock time. Each run owns its attempt counter.

Expected output:

```text
final value : success
loaded data : {'id': 42, 'name': 'Ada Lovelace'}
```

The actor receives the literal demo user ID `42`. This is fake data; no HTTP
request is made. Study `invoke`, `from_promise`, `onDone`, `onError`, and the
named guard/delay bindings. See [actors](../concepts/actors.md).

## Async workflow: await effects explicitly

[`async_workflow.py`](async_workflow.py) prints `completed async job 42` after
`await service.send(...)` has finished that event's async action. Its snapshot
subscription is synchronous. Use this runtime when machine actions need to be
awaited; consult the [runtime capability matrix](../concepts/runtimes.md) before
combining async actions with invoked actors or actor messaging.

## Snapshot resume: inspect, start, continue

[`snapshot_resume.py`](snapshot_resume.py) prints:

```text
before start: active; count=2
after resume: active; count=3
restored completed output: {'total': 3}
```

The old actor stops before the restored actor starts. Passing `snapshot=` at
construction avoids fresh chart initialization and makes that snapshot
available immediately. The program also preserves a computed final result
through JSON deserialization.

The JSON string stays in memory. This demonstrates serialization and actor
handoff, not durable storage or process-crash recovery. Timers, queued events,
child progress, and external side effects are outside this payload. Read the
[persistence contract](../concepts/persistence.md) before adding storage.

## Parallel traffic regions and SCXML import

The [traffic intersection](traffic_intersection.py) advances three parallel
regions and interrupts them with `EMERGENCY`. Its printed snapshots show
`initial`, timed changes, `PED_REQUEST`, `EMERGENCY`, and `CLEAR`. A
`SimulatedClock` makes those steps repeatable. The always-allow pedestrian
guard is a teaching stub; this chart is not a physical traffic-control policy.

The [SCXML toggle](scxml_toggle.py) imports the adjacent XML document and prints
`SCXML toggle returned to off` after two pure transitions. See the
[SCXML guide](../concepts/scxml.md) for the supported import subset.

Loading a shared JSON shape or an XML document does not establish general
cross-runtime equivalence. The [compatibility guide](../concepts/xstate-compatibility.md)
describes the actual pinned comparison cases and known differences.

## Advanced: controller and local inspector

The [docking controller](docking_controller.py) keeps resource handles outside
chart context and exposes typed application methods. Try its scripted paths:

```bash
python docs/examples/docking_controller.py
python docs/examples/docking_controller.py --scenario timeout
python docs/examples/docking_controller.py --scenario cancel
python docs/examples/docking_controller.py --trace-md docking-replay.md
```

The default path starts with `success: completed; commands:`. The timeout and
cancel paths end in `failed` and `cancelled`. The optional `--trace-md` command
writes a structural Markdown replay to the path you supply. The
[controller guide](../concepts/controllers.md) explains cleanup, concurrency,
and the limits of the recorded trace.

The [local inspector](local_inspector.py) is an interactive local HTTP server
for the synthetic fetch example:

```bash
python docs/examples/local_inspector.py
```

Open the loopback URL it prints and stop the server with Ctrl+C. It is excluded
from the one-shot command list because it intentionally keeps running. The
[inspector guide](../concepts/local-inspector.md) documents its controls,
privacy boundary, and dedicated tests.

## How the examples stay runnable

The primary suite runs every noninteractive Python example from a temporary
working directory, with a 30-second timeout per program. Behavioral tests
exercise the typed-context and revision-gate decisions, including invalid and
stale inputs. CI also type-checks both new examples.

The distribution validator installs the built wheel in a clean environment,
removes `PYTHONPATH`, and runs this same noninteractive collection from outside
the checkout. That catches source-only imports and accidentally undeclared
runtime dependencies. The interactive inspector has separate lifecycle tests.
See [contribution checks](../../CONTRIBUTING.md#public-examples-and-documentation)
for the commands.

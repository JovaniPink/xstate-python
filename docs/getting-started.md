# Getting Started

Use a statechart when the events your application accepts depend on its current
phase, or when several related phases, timers, and child operations need an
explicit lifecycle. Begin with a small chart and ordinary Python functions;
choose a runtime only when it needs to own actions or resources.

This guide takes you from a source installation to a running chart, then to the
[tested example catalog](examples/README.md). Python 3.13 or newer is required.

## Install The Library And Examples

The source candidate declares distribution name `xstate`, version `0.7.1`.
Publication and name ownership remain tracked in
[issue #57](https://github.com/JovaniPink/xstate-python/issues/57). Use this source
checkout for the APIs in these docs. Installing the unrelated public package
name with `pip install xstate` does not select this repository's source revision.

Clone the repository:

```bash
git clone https://github.com/JovaniPink/xstate-python.git
cd xstate-python
git rev-parse HEAD
```

Keep the printed commit SHA with any bug report or saved workflow result. It
identifies the code you installed; a branch name can move. To reproduce an
existing result, check out its recorded commit before installing.

On **macOS or Linux**, create and activate an environment:

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
```

On **Windows PowerShell**, use the Python launcher and the Windows activation
script. This command selects Python 3.13; use `-3.14` if that is your installed
supported version:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

In the activated environment, on either platform:

```bash
python -m pip install .
python -c "import xstate; print(xstate.__file__)"
python docs/examples/typed_context.py
```

The library has no runtime dependencies. Building the package still uses Python
packaging tools; you do not need Node, npm, a model provider, or an API key to
run the offline examples. The example scripts and companion JSON/SCXML files
remain in the checkout. The installed wheel exposes `xstate`, not a
`docs.examples` package.

The last command prints:

```text
Before resolution: reviewing; remaining=2
After resolution: original remaining=2; current remaining=0
After approval: done; output=ReviewResult(title='Release notes', approved=True)
```

For **contributing**, use the repository's locked development dependencies:

```bash
poetry install
poetry run python docs/examples/typed_context.py
```

The [contribution guide](../CONTRIBUTING.md) and
[development commands](../README.md#developing) cover lint, typing, tests, and
package validation. A normal `pip install .` installs the library, not that
development toolchain.

## Compute A Transition

Save this complete program as `hello_statechart.py`:

```python
from xstate import Machine

review = Machine(
    {
        "id": "review",
        "initial": "draft",
        "states": {
            "draft": {"on": {"SUBMIT": "reviewing"}},
            "reviewing": {
                "on": {"APPROVE": "approved", "REQUEST_CHANGES": "draft"}
            },
            "approved": {"type": "final"},
        },
    },
    strict=True,
)

state = review.initial_state
print(state.value)
state = review.transition(state, "SUBMIT")
print(state.value)
state = review.transition(state, "APPROVE")
print(state.value)
assert state.status == "done"
```

Run it with the same activated interpreter:

```bash
python hello_statechart.py
```

Output:

```text
draft
reviewing
approved
```

`Machine.transition` takes the current snapshot and an event and returns the
next snapshot. It does not own a running service or automatically execute
deferred effects. Guards and assignments execute while computing the result,
so keep those functions free of external side effects.

The configuration declares the allowed paths. An `APPROVE` event in `draft`
has no matching transition and leaves the chart there. `strict=True` validates
configuration keys and named implementations; it does not make every
unhandled event an error. The final `approved` state completes the machine,
after which further events cannot advance it.

## Let An Actor Own The Current State

Append this code to the same file. It reuses the `review` machine definition;
the new actor starts from that machine's initial state:

```python
from xstate import create_actor

actor = create_actor(review)
try:
    actor.start()
    actor.send("SUBMIT")
    assert actor.get_snapshot().value == "reviewing"
    actor.send("REQUEST_CHANGES")
    assert actor.get_snapshot().value == "draft"
    actor.send("SUBMIT")
    actor.send("APPROVE")
    assert actor.get_snapshot().status == "done"
    print("actor: approved")
finally:
    actor.stop()
```

The actor stores the current snapshot and executes its synchronous actions.
`try/finally` makes ownership explicit even when application code fails. A
completed or stopped actor does not restart; construct another actor for a new
operation. The [actor guide](concepts/actors.md) covers invocation, completion,
subscriptions, and cancellation.

## Add Python Data And Behavior

The [typed-context example](examples/typed_context.py) develops a release-note
review using a frozen dataclass, typed event mappings, and named Python
implementations:

| Concept | In the example | Responsibility |
| --- | --- | --- |
| State | `reviewing`, `approved` | Which transitions are available |
| Context | `ReviewContext(title, remaining)` | Data carried by the snapshot |
| Event | `RESOLVE` with a count, or `APPROVE` | Input that asks the chart to advance |
| Guard | A named Python predicate | Whether a particular transition is allowed |
| Assignment | A named `assign(...)` implementation | Produce the next context value |
| Output | `ReviewResult` | The completed operation's result |

Read it alongside [typing](concepts/typing.md) and
[handler arguments](concepts/machines-and-implementations.md#setup-and-handler-arguments).
Typed event declarations help static checking; the application still validates
untrusted input. A frozen dataclass adapter requires immutable nested values as
well as a frozen outer object. Use assignments for chart updates rather than
mutating context obtained from an actor snapshot.

## Choose A Runtime For The Work

| Need | API | Example |
| --- | --- | --- |
| Evaluate events without executing deferred effects | `Machine.transition` | [SCXML toggle](examples/scxml_toggle.py) |
| Execute synchronous actions and control timers | `interpret` | [Traffic intersection](examples/traffic_intersection.py) |
| Await machine actions in asyncio | `interpret_async` | [Async workflow](examples/async_workflow.py) |
| Invoke children or use actor messaging | `create_actor` | [Fetch with retry](examples/fetch_with_retry.py) |

The async interpreter does not start invoked actors. A machine actor can invoke
async child logic when its starting thread has an asyncio loop, but its own
machine actions remain synchronous. The
[runtime guide](concepts/runtimes.md) describes these boundaries and how action
failure differs from chart completion.

## Continue With A Concrete Example

1. **Python domain modeling:** run [typed context](examples/typed_context.py)
   and inspect a retained snapshot after an assignment.
2. **Software-development policy:** follow the
   [revision-gate walkthrough](guides/revision-gate.md). New code invalidates old
   CI and review evidence; scripted late results cannot make it ready.
3. **Runtime ownership:** work through [fetch with retry](examples/fetch_with_retry.py),
   [async actions](examples/async_workflow.py), and
   [snapshot resume](examples/snapshot_resume.py).
4. **Application integration and observation:** explore the
   [typed controller](concepts/controllers.md) and
   [local inspector](concepts/local-inspector.md).

Each example's commands and expected results are in the
[catalog](examples/README.md). Restoration preserves chart data according to the
[snapshot contract](concepts/persistence.md); it does not recover an application's
queues, deadlines, child progress, or external effects. The revision example
does not authenticate events or merge a real pull request.

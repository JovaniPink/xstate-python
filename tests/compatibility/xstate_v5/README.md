# Pinned XState v5 comparison

This development-only corpus executes the same literal JSON charts and command
sequences through **Python `create_actor`** and **JavaScript `createActor`**. It
is a small executable compatibility contract, not a second state-machine
implementation or a claim of complete XState support.

## Run

Use Node **24.22.1** and Python **3.13+**. From the repository root:

```sh
npm ci --ignore-scripts --no-audit --prefix tests/compatibility/xstate_v5
python scripts/compare_xstate_v5.py
```

The lockfile pins XState **5.33.4**, including its package integrity. The JS
runner rejects other Node or XState versions. The Python runner explicitly
imports this checkout's `src`, verifies the imported path, and reports the
Python version and the source distribution version. No Node dependency is
added to the Python runtime or distribution.

`--fixtures /path/to/fixtures.json` selects another corpus for a focused run or
to check the failure diagnostics. All command observations are compared with
hand-authored expected outcomes. Agreeing with the other runtime is insufficient:
both implementations must independently match their expected result.
An empty corpus, duplicate IDs, or missing command expectations is rejected
before execution. Error scenarios end at their failing command.

## Contract and representation

Each fixture contains a `chart`, optional numeric `delays` bindings, `commands`,
and `expected` observations for XState. A parity fixture uses those same
expectations for Python. A known difference also supplies a rationale and exact
`expected_python` observations. Any drift fails. Unexpected parity also fails
until the fixture is reviewed and promoted to the common expectation.

Every command records these fields:

- `time`: the native simulated clock's current milliseconds.
- `value`, `context`, `status`, `output`: the resulting machine snapshot.
- `actions`: ordered action observations during that command, including time,
  context, triggering event, and declared parameters.
- `children`: active child IDs in runtime order and ordered callback
  start/cleanup observations, including their generation and logical time.
- `errors`: command failures, with exact class/name and message. A failing
  command ends that scenario; an exception is never treated as a passing skip.

Only the following representation adapters are applied:

- Python's `Event(name, data)` is represented by its JSON object payload when
  supplied, or `{ "type": name }` for a payload-free event. Event names are not
  renamed. These fixtures do not claim internal timer-event spelling parity.
- JS `undefined` output/absent action parameters become JSON `null`, matching
  Python `None`. These fixtures test absent output; computed output and
  restoration remain separate work.
- JSON numbers such as `1000` and Python's `1000.0` compare by numeric value;
  booleans are not accepted as numbers.

The named implementation registries are deliberately small and equivalent:
`increment` uses each library's real `assign`, `raiseInner` raises the payload-free
`INNER` event using each library's supported constructor, `allowed` reads the
external event's Boolean `allow`, and `record` observes its actual handler
arguments. Python's `raise_` currently accepts a string; this corpus makes no
claim for arbitrary raised JSON payloads. The `worker` implementation is each
runtime's actual callback actor; a counter in that callback identifies starts
and their matching cleanups.

No adapter changes chart targets, state order, actions, timer resolution, or
execution semantics. The runners do not sort action or child observations.
Cleanup after the last command is resource teardown, outside the trace; the
child fixture explicitly exits its invoking state and checks that cleanup.

## What is covered

| Fixture | Required observation |
|---|---|
| `numeric-delay` | Literal `after: {"1000": "done"}` stays pending at 999 and completes at 1,000 ms. |
| `fractional-delay` | `"0.5"` remains pending at 0.25 and completes at 0.5 ms. |
| `exponent-delay` | `"1e3"` behaves as 1,000 ms. |
| `zero-delay` | `"0"` runs when the simulated clock is advanced by zero. |
| `numeric-delay-registry-collision` | The numeric after key wins over a same-named 2,000 ms registry entry. |
| `named-delay` | `WAIT` resolves to 750 ms; an intervening external event records its arguments at 500 ms. |
| `guard-assign-raise-eventless` | A false guard prevents movement; an accepted event assigns, raises, and completes through an eventless transition. |

These numeric examples establish the listed cases. They do not establish full
JavaScript `Number` coercion compatibility or arbitrary multiple-timer parity.

## Exact known differences

| Fixture | Python observation | Pinned JS observation |
|---|---|---|
| `causal-action-arguments` | Deferred actions see final context and the outer event. | Actions see the context and event at their position, including `INNER` for the raised/eventless steps. |
| `callback-child-reentry` | Explicit reentry retains child generation 1; a later exit cleans it up. | Reentry cleans up generation 1 and starts generation 2; the later exit cleans up generation 2. |
| `tied-delay-key-order` | JSON declaration order schedules `WAIT` first and reaches `named`. | JS object enumeration schedules numeric key `1000` first and reaches `numeric`. |
| `coarse-clock-cascade` | One 1,500 ms increment fires at 1,000 and 1,500, reaching `third`. | The clock advances to 1,500 before firing; the next 500 ms timer is due at 2,000, leaving `second`. |
| `missing-named-delay` | Startup raises `UnregisteredImplementationError`. | An undefined delay queues the after event immediately and reaches `done`. |

The first two are the action and lifecycle work packages in the proposed
roadmap. The missing-delay case records an intentional diagnostic boundary;
matching JS's immediate transition is not a requirement for this Python fix.

Both runners use their own **native `SimulatedClock`**. Parity cases advance to
timer boundaries. The separate coarse-clock fixture makes their differing
large-increment behavior visible; a shared fake clock would conceal it.

## Extending the corpus

Author the expected behavior from a documented semantic requirement before
running the adapters. Add only equivalent live bindings, preserving the shared
JSON chart. Do not generate expectations from runtime output, normalize away
surprising events, or turn a failing case into a broad expected-failure marker.
For a known difference, write both full observations and explain the boundary.

A failure names the fixture, zero-based command index, differing field,
expected/actual values, and runtime versions; the process exits nonzero.
The Python tests also verify that this checker rejects shared wrong results,
action-argument drift, and unexpected parity. Updating the reference version
requires reviewing the corpus and its known differences, not merely refreshing
the lockfile.

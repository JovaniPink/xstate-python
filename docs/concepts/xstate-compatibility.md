# XState Compatibility Contract

This library accepts XState-style data, but acceptance is not a guarantee that
every chart behaves like JavaScript XState. Compatibility is established per
fixture against **XState 5.33.4 on Node 24.22.1**. Other XState versions, including
v6, need their own evidence.

The [shared JSON fixtures and runners](../../tests/compatibility/xstate_v5/)
exercise the actual Python and JavaScript runtimes. Named actions, guards,
delays, and actor logic have equivalent test implementations on each side.
They are synthetic contracts, not a verified inventory of Stately exports.

## Run The Contract

From the repository root, with the Python development environment installed:

```bash
node --version  # v24.22.1
npm ci --prefix tests/compatibility/xstate_v5 --ignore-scripts --no-audit --no-fund
poetry run python scripts/compare_xstate_v5.py
```

The comparison job is separate from the ordinary Python matrix. Node and the
npm package are development tools; the Python distribution has no runtime
dependency on either.

Both executions are checked against independently specified expected outcomes
after each command. The contract includes logical time, snapshot value, context,
status, output, action-visible arguments and order, and child lifecycle logs in
the fixtures that exercise them. A mismatch identifies the fixture, command,
field, expected/actual values, and runtime versions. A known difference is an
exact expected observation, not a blanket skipped test. Unexpected parity also
fails until the corrected case is promoted to required parity.

The runner README owns the fixture format and the small representation adapters.
Those adapters do not discard actions or replace causal arguments with final
context to make the runtimes agree.

The current corpus contains **18 scenarios and 66 commands: 14 required-parity
cases and 4 exact known differences**. Causal action arguments and invoked-child
re-entry use the same expected observations in both runtimes.

## Numeric After Keys

JSON object keys are strings. This chart schedules a transition after 1,000 ms:

```json
{
  "id": "timeout",
  "initial": "waiting",
  "states": {
    "waiting": {"after": {"1000": "elapsed"}},
    "elapsed": {}
  }
}
```

The parser recognizes finite, nonnegative JSON-number spellings:

```text
(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?
```

Examples include `"0"`, `"1000"`, `"0.5"`, `"1e3"`, and `"1e-2"`.
They denote milliseconds. A matching key that overflows to infinity, such as
`"1e309"`, raises `InvalidConfigError` at construction with its configuration
path. Very small values follow floating-point conversion, including underflow
to zero. Zero schedules a timer; with `SimulatedClock`, call `increment(0)` to
flush it.

Other strings remain named delays. Register `"reviewTimeout"` through
`Machine(config, delays={"reviewTimeout": 1000})`, or bind a callable to compute
its duration. Missing names raise `UnregisteredImplementationError` when used.
This grammar deliberately does not implement JavaScript's entire numeric
coercion: `"+1"`, `"001"`, `" 1 "`, `"0x10"`, `"-1"`, `"Infinity"`, and the empty
string remain registry names. Existing numeric Python dictionary keys and
registry values retain their prior behavior; this is not a redesign of all
duration validation.

### Migration For Numeric Registry Names

`after: {"1000": ...}` now means 1,000 ms even when `delays["1000"]` exists.
Previously that string selected the registry. This matches the pinned reference
for supported numeric keys. To retain a configurable duration, rename the
`after` key and its registry entry to a descriptive name, for example
`"reviewTimeout"`.

The conversion is specific to `after`. `send(..., delay="1000")` still looks up
`delays["1000"]`; it does not become a numeric duration. The shared resolver and
the sync/async scheduling ownership remain unchanged.

## Causal Action Arguments

Each deferred action captures context through `ContextAdapter.snapshot` at its
position in the action sequence, together with the current event and declared
parameters. This applies to named and inline effects, entry/exit actions, and
actions expanded by `choose` or `pure`. Raised and eventless microsteps retain
their effective event. The final macrostep and its microstep traces use the
same captured arguments; collecting a trace does not execute the effects.

The `causal-action-arguments` fixture requires a record before an assignment to
see `n=0`, the record after it to see `n=1`, and the raised/eventless actions to
see `INNER` rather than the outer `GO` event. Its original XState expectations
are now required for Python too. This establishes that sequence, not general
action or actor compatibility.

### Migration For Action Handlers

Previously deferred handlers could observe the final macrostep context and
outer event regardless of their position. Handlers now receive the context
and event that caused that action. Use `assign` for chart context updates:
with the default adapter, mutating an action's captured context changes neither
the committed snapshot nor another action's context.

Event payloads and action parameters remain references, not deep copies;
callable action parameters remain opaque values. Custom context adapters
define context ownership. See the [handler contract and context policy](machines-and-implementations.md#action-arguments-and-migration)
and the [runtime boundary](runtimes.md#action-arguments-and-committed-state)
for committed snapshots, delayed sends, and copying costs.

## Re-entry And Completion

JSON transitions default to `reenter: false`. Explicit `reenter: true` resets
resources owned by a state that exits and re-enters; retained states keep their
timer deadlines and invoked children. `reenter` must be a Boolean. An explicit
legacy `type` retains its transition policy when `reenter` is absent, and SCXML
import preserves its external default. Existing JSON charts that relied on
implicit external self/descendant transitions need an explicit reset policy;
see [re-entry migration](machines-and-implementations.md#re-entry-and-migration).

The comparison checks child replacement, timer reset, retained resources on
targetless/self/descendant transitions, and final completion. Completed machine
runtimes release their owned work and ignore later events; pure transitions
from a done snapshot emit no actions. The original child-reentry XState oracle
is now required for Python too. These fixtures establish the listed lifecycle
sequences, including initially final machines.

The runner records `children.ids`, preserving each runtime's child-reference
keys without filtering. A completed XState snapshot can retain a stopped
root-invocation reference that Python removes. The exact known-difference case
requires the same cleanup callback and ignored post-completion events on both
sides; retained-reference representation is distinct from failed cleanup.

## Current Evidence Limits

The passing fixtures establish the checked command sequences. They do not
imply general parity for timer ordering, action execution, or actors.

| Boundary | Current limit |
|---|---|
| Invocation and delay arguments | Ordinary `invoke.input` and state `after` expressions use committed context and the outer event, not per-entry argument captures |
| Startup ordering | JavaScript child startup and entry-effect ordering can differ; lifecycle fixture parity does not establish general startup-order parity |
| Parallel transition domains | Modern `reenter` rules and explicit legacy/SCXML transition-domain rules are separate policies, not globally equivalent |
| Completed child references | XState can retain stopped root-invocation references in completed snapshots; Python removes the owned children after cleanup |
| Tied delays | JavaScript enumerates array-index-shaped object keys before other keys; Python preserves declaration order, which can select a different transition at the same deadline |
| Numeric aliases | Different keys such as `"1000"` and `"1e3"` can share an internal event identity in JavaScript; equivalent-duration multi-key charts are outside the claimed parity subset |
| Large simulated-time jumps | Python executes chained timers at their due times; JavaScript's simulated clock advances to the target before callbacks. One large jump can produce different states |
| Missing or unusual delays | Python's missing-name errors and bounded numeric grammar deliberately differ from JavaScript coercion/fallback behavior |
| Persistence | Lifecycle checks do not turn a serialized snapshot into a complete restartable execution checkpoint |

For ordinary parity timing fixtures, commands end at explicit deadlines. Known
clock differences are retained separately; neither clock is rewritten by the
comparison runner. No universal timer or lifecycle compatibility is claimed.

## What This Enables Next

The next product gate is a representative application or Stately export that
runs in both runtimes without rewriting its structure. Supply equivalent named
implementations, compare observable behavior, and measure transition cost with
the application's context size and copying policy. Synthetic fixture parity
does not establish consumer adoption or acceptable application performance.

The [product notes](../PRODUCT.md) separate that compatibility milestone from
an optional workflow host, framework integrations, and package identity work.
This implements a first slice of [#55](https://github.com/JovaniPink/xstate-python/issues/55)
and the [roadmap proposal](https://github.com/JovaniPink/xstate-python/pull/59),
not the complete compatibility roadmap.

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

## Current Evidence Limits

The passing delay fixtures establish the checked command sequences. They do
not imply general parity for timer ordering, action execution, or actors.

| Boundary | Current limit |
|---|---|
| Action arguments | Deferred Python effects can see final context and the outer event rather than the context/event at the action's position |
| Re-entry and child lifecycle | Entry/exit behavior and invoked child replacement differ; the comparison retains the observed child start/cleanup sequence |
| Tied delays | JavaScript enumerates array-index-shaped object keys before other keys; Python preserves declaration order, which can select a different transition at the same deadline |
| Numeric aliases | Different keys such as `"1000"` and `"1e3"` can share an internal event identity in JavaScript; equivalent-duration multi-key charts are outside the claimed parity subset |
| Large simulated-time jumps | Python executes chained timers at their due times; JavaScript's simulated clock advances to the target before callbacks. One large jump can produce different states |
| Missing or unusual delays | Python's missing-name errors and bounded numeric grammar deliberately differ from JavaScript coercion/fallback behavior |
| Final completion and persistence | A done snapshot alone does not prove child cleanup, terminal runtime behavior, or a complete restartable execution checkpoint |

For ordinary parity timing fixtures, commands end at explicit deadlines. Known
clock differences are retained separately; neither clock is rewritten by the
comparison runner. No universal timer or lifecycle compatibility is claimed.

## What This Enables Next

The next core improvement is causal action binding: preserve the context,
event, and parameters belonging to each deferred action, then promote its
known-difference fixture to required parity. Re-entry and completion need their
own resource-lifecycle changes and fixtures.

Before promoting the broader shared-chart product claim, validate a
representative application or Stately export without rewriting its structure.
The [product notes](../PRODUCT.md) separate that compatibility milestone from
an optional workflow host, framework integrations, and package identity work.
This implements a first slice of [#55](https://github.com/JovaniPink/xstate-python/issues/55)
and the [roadmap proposal](https://github.com/JovaniPink/xstate-python/pull/59),
not the complete compatibility roadmap.

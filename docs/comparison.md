# Python State Machine Library Comparison

Research snapshot: June 2026. Competitor figures are intentionally approximate;
the xstate-python column reflects the current `master` branch after the 0.6.0
release-readiness work.

## Feature Matrix

| Feature | **transitions** | **python-statemachine** | **xstate-python** | **xstate-statemachine** | **Sismic** | **Automat** |
|---|---|---|---|---|---|---|
| Status | Mature / active | Mature / active | Alpha / 0.6.0 release-ready | Small active project | Mature niche | Mature focused FSM |
| Python support | Broad legacy support | Modern Python | **3.13+** | Modern Python | Modern Python | Modern Python |
| XState JSON | No | No | **Yes, native** | Yes | No | No |
| SCXML algorithm | No | Yes | **Yes, partial conformance** | Partial | Yes | No |
| Hierarchical states | Yes, extension | Yes | Yes | Yes | Yes | No |
| Parallel states | Yes, extension | Yes | Yes, with known SCXML `more-parallel` gaps | Yes | Yes | No |
| Guards/actions | Yes | Yes | Yes, named or inline | Yes | Yes | Limited |
| Context/extended state | No native XState-style context | Yes | Yes, with `assign` and snapshot isolation | Yes | Yes | No |
| Eventless transitions | No | Yes | Yes, `always` and legacy empty-event form | Yes | Yes | No |
| Delayed transitions | Yes | Yes | Yes, `after` with pluggable clocks | Yes | Yes | No |
| Sync runtime | Yes | Yes | Yes, RTC `Interpreter` | Yes | Yes | Yes |
| Async runtime | Yes | Yes | Yes, `AsyncInterpreter` | Yes | Yes | No |
| Actor model | No | No | Yes, XState v5-style actors | Partial | No | No |
| Invoke/services | No | Yes | Yes, `invoke` + promise/callback/observable actors | Yes | No | No |
| Setup-style named implementations | No | No | Yes, `setup(...).create_machine(...)` | Partial | No | No |
| Snapshot tags/meta | No | Yes, metadata-style helpers | Yes, active tags/meta on snapshots | Partial | Yes | No |
| Diagram export | Yes, GraphMachine | Yes | Yes, Mermaid text export | Partial | Yes | No |
| Runtime dependencies | Varies | Varies | **None for core** | Varies | Varies | Small |
| Docs quality | Good | Excellent | Improving | Good | Excellent | Good |
| License | MIT | MIT | MIT | MIT | LGPL-3.0 | MIT |

## Where xstate-python Fits

`xstate-python` is not trying to be the broadest Python FSM library. Its
differentiator is the combination of:

- Native XState/Stately JSON compatibility.
- SCXML-style run-to-completion semantics.
- XState v5 concepts such as actors, `invoke`, `setup`, `MachineSnapshot`,
  `guard`, `output`, and `always`.

That makes it a good fit when a Python service needs to share statechart
structure with a JavaScript/XState frontend or a Stately-authored design.

## Current xstate-python Capabilities

- Hierarchical and parallel states.
- Entry, exit, transition, assign, raise, send, cancel, parent, and targeted
  actor actions.
- Guards as named implementations, inline callables, or strict `setup`
  handlers.
- Context updates through `assign`, with deep-copy default isolation and an
  immutable dataclass adapter.
- Eventless transitions, final states, `onDone`, shallow/deep history, and
  delayed `after` transitions.
- Synchronous `Interpreter` with a run-to-completion queue and thread-safe timer
  callback serialization.
- `AsyncInterpreter` for asyncio runtimes and awaitable action side effects.
- Actor model with `create_actor`, `ActorSystem`, `spawn`, `from_promise`,
  `from_callback`, `from_observable`, `to_promise`, `send_parent`, `send_to`,
  and `invoke` reconciliation.
- Snapshot serialization and restoration helpers for persistence flows.
- Active snapshot `tags`, `meta`, `has_tag`/`hasTag`, and
  `state_in`/`stateIn` guard helpers on the 0.7.0 branch.
- Dependency-free Mermaid diagram export via `to_mermaid(machine)` on the
  0.7.0 branch.
- SCXML XML import with a safe Boolean cond subset: `true`, `false`, `!`, `&&`,
  `||`, and parentheses.

## Known Gaps

| Gap | Notes |
|---|---|
| PyPI release | 0.6.0 packaging metadata and release workflow are ready; publish via GitHub Release. |
| SCXML conformance | Current full SCXML run is `45 passed`, `8 failed`; remaining failures are the known `more-parallel` cases. |
| Full ECMAScript cond support | Intentionally not implemented; unsupported SCXML expressions raise `InvalidConfigError`. |
| Graph/test utilities | Mermaid export exists on the 0.7.0 branch; no graph traversal/test-path helpers yet. |
| Inspector protocol | No `@statelyai/inspect` compatibility yet. |

## Strategic Position

`transitions` and `python-statemachine` are excellent general-purpose Python
libraries. `xstate-python` earns its place when XState JSON compatibility is the
requirement: Stately designs, shared frontend/backend machine configs, and
XState v5 actor-style runtime patterns in Python.

# Python State Machine Library Comparison

Research snapshot: June 2026. Competitor figures sourced from PyPI, GitHub, and each library's
documentation. The xstate-python column reflects the current state of this repo (0.3.x / 0.5.0
actor branch), not the dormant upstream.

## Feature Matrix

| Feature | **transitions** | **python-statemachine** | **xstate-python** *(this project)* | **xstate-statemachine** *(basiltt)* | **Sismic** | **Automat** |
|---|---|---|---|---|---|---|
| **Stars / Status** | ~6,500 / Active | ~1,200 / Active | ~194 / Active (fork) | ~14 / Active | ~163 / Active | ~647 / Active |
| **Latest release** | 0.9.3 (Jul 2025) | 3.1.2 (May 2026) | WIP (no PyPI release yet) | 0.5.0 (Mar 2026) | 1.6.11 (Oct 2025) | 25.4.16 (Apr 2025) |
| **Python support** | 2.7, 3.8–3.13 | >=3.9 | 3.9–3.13 | >=3.9 | >=3.9 | >=3.9 |
| **Hierarchical states** | Yes (ext) | Yes (v3.0+) | Yes | Yes | Yes (full UML2) | No |
| **Parallel states** | Yes (ext) | Yes (v3.0+) | Yes (full — broadcast, nested, onDone) | Yes | Yes | No |
| **Guards / Conditions** | Yes | Yes | Yes (callable or named, arity-aware) | Yes | Yes | No |
| **Entry/Exit actions** | Yes | Yes | Yes | Yes | Yes | No |
| **History states** | Yes (ext) | Yes (v3.0+) | Yes (shallow + deep) | Yes | Yes (shallow+deep) | No |
| **Delayed transitions** | Yes (thread-based) | Yes (v3.0+) | Yes (`after` — SimulatedClock / ThreadClock) | Yes | Yes | No |
| **Event queue** | Yes (queued mode) | Yes (v3.0+) | Yes (RTC queue in Interpreter) | Yes | Yes | No |
| **Async support** | Yes (AsyncMachine) | Yes (auto-detect) | Planned (0.5.0 target) | Yes | Yes | No |
| **SCXML compliance** | No | Yes (W3C test suite) | Partial (XML import; JS cond eval via optional extra) | Partial (XState JSON) | Yes (SCXML 1.0) | No |
| **XState JSON format** | No | No | **Yes (native — the differentiator)** | Yes (Stately.ai export) | No | No |
| **Eventless transitions** | No | Yes (v3.0+) | Yes (`always:`) | Yes | Yes | No |
| **`invoke` / services** | No | Yes (v3.0+) | Yes (`invoke:` + `from_promise`/`from_callback` — 0.5.0) | Yes | No | No |
| **Actor model** | No | No | Yes (`create_actor`, `ActorSystem`, `spawn`, `send_parent`/`send_to` — 0.5.0) | Partial | No | No |
| **Context + assign** | No | Yes | Yes (`assign` action, deep-copy isolation) | Yes | Yes | No |
| **Type safety** | Partial (.pyi stubs) | Partial | Partial (`from __future__ import annotations` throughout) | Yes (generics) | Partial | Yes (Protocol) |
| **Visualization** | Graphviz, Mermaid | Graphviz, Mermaid | Basic (`viz.py`) | Mermaid, PlantUML | PlantUML | Graphviz |
| **Testing utilities** | None dedicated | None dedicated | pytest suite (166 tests, SimulatedClock for deterministic timing) | Yes (snapshot) | Yes (BDD, DbC) | None dedicated |
| **Design by Contract** | No | No | No | No | Yes | No |
| **Docs quality** | Good | Excellent | Minimal | Good | Excellent | Good |
| **License** | MIT | MIT | MIT | MIT | LGPL-3.0 | MIT |

## Where xstate-python Stands Today

**Implemented (0.3.x / 0.5.0-actor branch):**

- Hierarchical (compound) states, parallel states (broadcast events, nested parallel, `onDone`)
- Entry/exit actions, guards (callable or named string, arity-aware `(context, event)`)
- Context + `assign` actions with deep-copy isolation between snapshots
- Final states + `onDone` transitions; `always:` (eventless) transitions
- History states — shallow and deep
- Synchronous `Interpreter` with run-to-completion event queue, `subscribe()` listeners
- Delayed transitions (`after`) driven by pluggable `Clock` — `SimulatedClock` (deterministic) or `ThreadClock` (real time)
- Actor model (0.5.0): `create_actor`, `Actor`, `ActorSystem`, `spawn`, parent/child tree
- `invoke:` wiring — a child actor runs for a state's lifetime, with `onDone`/`onError`
- Actor logic kinds: `from_promise` / `from_callback`
- Inter-actor messaging: `send_parent` / `send_to`
- XState v5 config alignment: `guard`, `output`, `always`, `MachineSnapshot`, single-object handler signatures (0.4.0)
- SCXML XML import (requires `pip install xstate[scxml]` — JS cond eval no longer a hard dep)

**Still to implement:**

| Priority | Gap |
|---|---|
| High | PyPI publish (no release yet) |
| High | Async interpreter (`asyncio`-based) + true deferred promise resolution (0.5.0/0.6.0) |
| Medium | Pure-Python SCXML condition evaluator (replace JS eval entirely) |
| Low | `setup()` API + composable guards (0.6.0) |
| Low | Visualization (Mermaid export) |

## Strategic Position

The differentiating niche is **native XState / Stately.ai JSON compatibility**. Neither `transitions`
nor `python-statemachine` accepts XState JSON natively. Users who design machines in the
[Stately.ai editor](https://stately.ai/editor) or share config across JS and Python codebases
have no other well-maintained option.

`python-statemachine` is the strongest competitor on raw features (SCXML compliance, async,
invoked services). The path to differentiation is not feature parity — it is owning the
XState JSON import/export pipeline and tracking XState v5's actor model in Python.

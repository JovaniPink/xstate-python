# xstate-python — Project Context for AI Agents

## What this is

A Python implementation of [XState](https://github.com/statelyai/xstate) — statecharts and
hierarchical state machines for Python, following the W3C SCXML execution algorithm. The goal is
a **solid, published Python statechart library** that tracks XState v5's architecture and owns
the niche of native XState JSON compatibility.

**PyPI name:** `xstate` | **License:** MIT | **Python:** 3.13+

---

## Architecture

```
src/xstate/
  __init__.py       Public API: `from xstate import Machine`
  machine.py        Machine class — entry point and pure transition API
  config_parser.py  Two-pass XState config parser and normalizer
  schema.py         TypedDict boundary for raw XState config data
  state_node.py     Resolved state hierarchy model
  state.py          Public State / MachineSnapshot snapshots
  algorithm.py      SCXML execution engine (microstep/macrostep, entry/exit sets)
  transition.py     Resolved transition model
  handlers.py       HandlerArgs and HandlerAdapter callable adaptation
  guards.py         Composable guards and state_in/stateIn helpers
  mermaid.py        Dependency-free Mermaid diagram export
  actor.py          Actor model, create_actor, ActorSystem, actor logic helpers
  scxml.py          SCXML XML → Machine config converter with safe Boolean conds
```

`algorithm.py` is the heart of the library. It implements the W3C SCXML algorithm:
`compute_entry_set`, `enter_states`, `exit_states`, `microstep`, `main_event_loop`.
The critical execution order is: `main_event_loop` → `microstep` → `main_event_loop2`
(which handles eventless transitions / `always` blocks after each macrostep).

---

## Current state (0.6.0 release-ready, 0.7.0 branch in progress)

**Working:**
- Hierarchical (compound) states
- Parallel states (`type: "parallel"`) — independent regions, broadcast events,
  nested parallel, `onDone` when all regions reach a final state
- Entry / exit actions
- Guards / conditions (pure Python): `cond` as a callable `(context, event)` or a
  string resolved from `Machine(config, guards={...})`
- Context + `assign` actions (`from xstate import assign`); event payloads reach
  guards/assigners via `event.data` (pass `transition(state, {"type": ..., ...})`)
- Final states + `onDone` transitions
- History states — shallow and deep (`{"type": "history", "history": "deep"}`),
  persisted across transitions via `State.history_value`
- **Interpreter** (`from xstate import interpret`) — running instance with
  `start()`/`stop()`/`send()`, run-to-completion event queue, `subscribe()`
  listeners, and side-effect action execution
- **Delayed transitions** (`after: {1000: "target"}`) — scheduled on entry,
  cancelled on exit; numeric delays or named refs via `Machine(config, delays={...})`.
  Driven by a pluggable `Clock`: `SimulatedClock` (deterministic, advance with
  `clock.increment(ms)`) or `ThreadClock` (real wall-clock, the default)
- SCXML XML import with a dependency-free safe Boolean cond subset
  (`true`, `false`, `!`, `&&`, `||`, parentheses)
- **XState v5 config alignment** (0.4.0):
  - `guard` is the canonical key for transition conditions; `cond` still works
    but emits a `DeprecationWarning`
  - `output` is the canonical key for final-state data; `data` still works but
    emits a `DeprecationWarning`
  - `always:` for eventless transitions (alongside the v4 `on: {"": ...}` form)
  - Single-object handler signatures via keyword-only params:
    `def guard(*, context, event): ...` (the v5 `({context, event}) =>` shape).
    The v4 positional styles still work — see the handler-signature note below
  - `MachineSnapshot` (public alias of `State`) carries `status`
    (`"active"`/`"done"`/`"error"`), `output`, and `error`; plus `state.matches()`
    and `state.can(event)`
- **Actor model** (0.5.0, `from xstate import create_actor`) — `Actor` + `ActorSystem`
  with `id`/`parent`/`children`, `spawn`, `from_promise`/`from_callback` logic,
  `send_parent`/`send_to`, and `invoke:` child-actor reconciliation feeding back
  `done.invoke.<id>` / `error.platform.<id>`
- **Async actors** (0.5.0) — a coroutine `from_promise` and `from_observable`
  schedule their work as an `asyncio.Task` and resolve / emit on the event loop
  (a plain `from_promise` still resolves eagerly); `to_promise(actor)` adapts any
  actor to an `asyncio.Future`. Async `invoke:` children feed `done.invoke.<id>` /
  `error.platform.<id>` back to a machine parent once their task settles
- **AsyncInterpreter** (0.5.0, `from xstate import interpret_async`) — asyncio-native
  runtime: `await start()`/`send()`/`stop()`, run-to-completion event queue,
  **awaitable action callables** (`async def` side effects are awaited), and
  `after` delayed transitions scheduled on the event loop. The pure transition /
  guard layer stays synchronous, so `algorithm.py` is shared with the sync runtime

- **Composable guards** (0.6.0, `from xstate import and_, or_, not_`) — `and_()`,
  `or_()`, `not_()` combinators; string sub-guards resolved lazily from machine.guards
- **`setup()` builder** (0.6.0, `from xstate import setup`) — XState v5 setup pattern:
  `setup(guards=..., actions=..., delays=..., actors=...).create_machine(config)`
- **Snapshot serialization** (0.6.0, `from xstate import serialize_snapshot, deserialize_snapshot`)
  — persist and restore State; `create_actor(machine, snapshot=...)` for round-trip replay
- **Snapshot queries** (0.7.0 branch) — active `tags`, read-only `meta`,
  `state.has_tag(...)`, `state.hasTag(...)`, and `state_in(...)` / `stateIn(...)`
- **Mermaid export** (0.7.0 branch, `from xstate import to_mermaid`) —
  dependency-free `stateDiagram-v2` text generation
- **State tags** (0.7.0) — declare `tags: ["loading"]` (or a single string) on any state node;
  query the snapshot with `state.has_tag("loading")` / `state.hasTag(...)` or read the aggregated
  `state.tags` frozenset. Tags union across the whole active configuration (compound ancestors +
  parallel regions) and are recomputed from the machine definition, so snapshots stay tag-free
- **`state_in` / `stateIn` guard** (0.7.0, `from xstate import state_in, stateIn`) — first-class guard over the current
  configuration: `state_in("#id")`, `stateIn("parent.child")`, or `stateIn({parent: child})`.
  Composes with `and_`/`or_`/`not_` and can be registered as a named guard; it reuses the same
  matcher as the internal transition `in` guard (`algorithm._matches_in_state`)
- **`choose` / `pure` actions** (0.7.0, `from xstate import choose, pure`) — higher-order actions
  that expand into sub-actions at execution time. `choose([{guard, actions}, ...])` runs the first
  branch whose guard passes (a guardless branch is the default); `pure(fn)` runs the action(s)
  returned by `fn(context, event)` (or none). Both are resolved inside `algorithm.execute_content`,
  so nested `assign`/`raise_`/`send`/side-effects flow through the engine in order. `choose` branch
  guards see `(context, event)` but not the configuration, so `stateIn` isn't supported inside them

Handler-signature note: public registries are adapted at machine construction by
`HandlerAdapter`. Prefer `handler(HandlerArgs(...))`; legacy `()`, `(context)`,
`(context, event)`, and keyword-only forms still work at the compatibility
boundary.

---

## Release roadmap

| Version | Theme | Key deliverables |
|---------|-------|-----------------|
| 0.1.0 | Capture & stabilize | Engine bug fixes, drop Js2Py hard dep, modern packaging, PyPI publish |
| 0.2.0 | Solid v4 FSM | Guards/conditions (pure Python), deep history, context/assign, full parallel |
| 0.3.0 | Interpreter | Synchronous event loop + queue, delayed transitions (`after`/`cancel`) |
| 0.4.0 | v5 config alignment | Rename `cond`→`guard`, `data`→`output`, `always:`, single-object handler signatures, MachineSnapshot |
| 0.5.0 | Actor model | `create_actor`, actor system, `from_promise`/`from_callback`, asyncio |
| 0.6.0 | Setup & parity | `setup()`, composable guards (`and_`/`or_`/`not_`), snapshot serialization |
| 0.7.0 | Next parity | State `tags` + `hasTag()`, `stateIn` guard, Mermaid diagrams; next: `choose`/`pure` actions, Graphviz diagrams, TypedDict config schemas |
| 0.8.0+ | Internal refactor | `StateNodeConfigParser` factory, opt-in immutable `context_factory`, `ParamSpec` handler typing |

The differentiating niche: **XState / Stately.ai JSON compatibility** — neither `transitions`
nor `python-statemachine` accepts XState JSON natively.

---

## Architectural debt (deferred, tracked)

These items came out of an architectural review. Each is intentionally deferred with a
target version; do not silently "fix" them outside their milestone, because they touch the
public API or the SCXML core and need the verification gates below.

| # | Item | Where | Status / plan |
|---|------|-------|---------------|
| 1 | **Dynamic handler arity** — `algorithm._invoke` / `handlers.invoke_handler` inspect a callable's signature on every call to support 4 calling conventions | `algorithm.py`, `handlers.py` | Short-term approach (signature inspection cached via `functools.lru_cache`) is fine. Moving to a single `Callable[[HandlerArgs], Any]` + `ParamSpec` contract is a **breaking** API change — defer to **0.8.0+** after `setup()` is stable. |
| 2 | **Parser/model separation** — `StateNode` is already a pure dataclass, but some normalization responsibilities still sit close to the model boundary | `state_node.py`, `config_parser.py` | Master already extracted `config_parser.StateNodeConfigParser`. Finish consolidating raw-config traversal, defaults, and transition normalization in the parser so `StateNode` stays a resolved model. Safe only **after** item 3 (typed inputs). Target **0.8.0+**. |
| 3 | **`Any` config boundary → TypedDict** — `Machine(config: dict[str, Any])` loses all static checking | `schema.py`, `machine.py` | Master added `schema.py` with `StateNodeConfig`/`TransitionConfig`/`InvokeConfig`/`MachineConfig` TypedDicts. Next: type `Machine(config: MachineConfig)` and enable stricter mypy on `machine.py` progressively. Target **0.7.0**. |
| 4 | **`deepcopy` context cost** — context is `deepcopy`-ed on each transition | `context.py` | Master added `ContextAdapter` (`DeepCopyContextAdapter`, `DataclassContextAdapter`). Expose the adapter as a documented `context_factory`-style hook so power users opt into immutable/cheaper structures. Target **0.7.0+**. |
| 5 | **IIFE lambda binding** — `(lambda e: lambda: self.send(e))(event)` | `interpreter.py` | ✅ **Done** — replaced with `functools.partial(self.send, event)` (0.6.0). |

**Verification gates for any of the above:**
- Changes to `algorithm.py` (item 1) must pass the SCXML test framework (`tests/test_scxml.py`,
  see "Algorithm changes require SCXML test verification" below).
- Parser/model changes (item 2) must pass parser, transition, and SCXML import coverage; run full
  SCXML conformance only if they alter transition selection or entry/exit semantics.
- Public-API changes (items 1, 3, 4) must keep the v0.1.0 contract or land in a minor bump
  with a `DeprecationWarning` bridge, matching how `cond`→`guard` was handled in 0.4.0.

---

## 0.7.0 feature backlog (research-informed)

Targets drawn from XState v5 (https://stately.ai/docs/xstate) and the Python statechart
landscape (`transitions`, `python-statemachine`, `Sismic`). Ranked by parity value × differentiation.

**XState v5 parity gaps:**
- **State `tags`** — ✅ on 0.7.0 branch: `tags: ["loading"]` in config; `state.has_tag("loading")` and `state.hasTag("loading")` on `MachineSnapshot`.
- **`choose` action** — conditional action selection (run the first branch whose guard passes).
- **`pure` action** — a function returning a list of actions to run, with no side effects of its own.
- **`stateIn` guard** — ✅ on 0.7.0 branch: user-facing guard over the current configuration, exposed as `state_in(...)` and `stateIn(...)`.
- **`enqueueActions`** — batch/queue actions imperatively inside an action body.
- **Transition `reenter: true`** — re-enter the source state on a self-transition (vs. internal).
- **`stopChild` action** — explicitly stop a spawned/invoked actor.
- **Dynamic `sendTo` targets** — `to=` resolved from `(context, event)`.
- **Machine / state `meta`** — ✅ on 0.7.0 branch: per-node metadata surfaced via read-only `state.meta`.
- **Partial event descriptors / wildcard** — `on: {"UPDATE.*": ...}` style matching.

**Differentiators worth owning (gaps in the Python field):**
- **Mermaid / Graphviz diagram export** — Mermaid export is ✅ on 0.7.0 branch via `to_mermaid(machine)`; Graphviz remains deferred.
- **`hasTag` / `can` / `matches` snapshot ergonomics** — `has_tag` / `hasTag`, `can`, and `matches` are present.
- **Observer pattern** — `python-statemachine`'s `add_observer`; we have `subscribe`, consider a
  multi-callback observer protocol with entry/exit hooks.

**Process note:** a deep-research workflow over the four comparison libraries was scoped in this
session (see `deep-research` skill invocation) but not yet run to completion; re-run it before
locking the final 0.7.0 scope to confirm method signatures and catch anything new upstream.

---

## Development commands

```bash
# Install dev deps
poetry install

# Run the test suite (primary target — no extras needed)
python3 -m pytest tests/ --ignore=tests/test_scxml.py

# Run SCXML tests (needs test-framework submodule and the scxml extra)
git submodule update --init
pip install xstate[scxml]
python3 -m pytest tests/test_scxml.py

# Type check
mypy src/xstate/

# Format + lint
ruff format src/ tests/
ruff check src/ tests/
```

---

## Key constraints and guardrails

### Never reintroduce Js2Py as a hard dependency

`Js2Py` cannot build on modern Python and is a security anti-pattern for a
library. The SCXML importer now uses a small pure-Python Boolean evaluator.
**Do not reintroduce `js2py` or a general JavaScript evaluator anywhere in
`xstate/`.**

### Algorithm changes require SCXML test verification

`xstate/algorithm.py` implements the W3C SCXML algorithm. Any change to it must be
verified against the SCXML test framework (`test-framework/`). The reference is:
https://www.w3.org/TR/scxml/#AlgorithmforSCXMLInterpretation

Key functions and their SCXML algorithm counterparts:
- `compute_entry_set` → `computeEntrySet`
- `add_descendent_states_to_enter` → `addDescendantStatesToEnter`
- `add_ancestor_states_to_enter` → `addAncestorStatesToEnter`
- `main_event_loop` / `main_event_loop2` → `mainEventLoop` / `macrostep`
- `get_transition_domain` → `getTransitionDomain`
- `get_proper_ancestors` → `getProperAncestors`

### API surface (v0.1.0 public contract)

```python
from xstate import Machine

# Construct a machine from a Python dict (XState JSON shape)
machine = Machine(config: dict, actions: dict = {})

# Get the initial state
state = machine.initial_state   # State(value, configuration, context, actions)

# Transition
state = machine.transition(state, "EVENT_NAME")

# State values
state.value   # str for atomic states, dict for compound: {"parent": "child"}
```

**Do not break this interface in 0.1.x patches.** API changes go in 0.4.0 (v5 alignment).

---

## Upstream remotes

```
origin    → JovaniPink/xstate-python  (your fork — push here)
upstream  → statelyai/xstate-python   (original; dormant after 2021)
```

Notable upstream branches:
- `upstream/master` — last upstream commit ~2021; use as historical reference only
- `upstream/davidkpiano/parallel+interrupt` — maintainer's engine bug fixes (already merged into 0.1.0)

PR #49 on upstream (`auphofBSF/tests/extend_testing_21w38`) was evaluated and intentionally
**not** adopted. Reason: it welds the codebase to Js2Py (its headline feature is pasting
JavaScript config), contains Python-3-invalid `raise "<string>"` bugs, and adds 8k lines
of v4-style code while the maintainer signalled the project should target v5. Its
**test corpus** (`test_history.py`, `test_state_in.py`) is the valuable artifact and should
be ported as behavior targets in 0.2.0.

---

## Target alignment: XState v5

The JS library lives at https://github.com/statelyai/xstate (packages/core).

Key v5 concepts for Python alignment:
- `createMachine` + `setup()` replace `Machine()` (0.6.0+)
- `createActor(logic)` replaces `interpret(machine)` (0.5.0)
- All handlers use single-object signature: `guard({"context": c, "event": e})`  (0.4.0)
- `State` → `MachineSnapshot` with `{status, value, context, output, error}` (0.4.0)
- `cond` → `guard`, `data` → `output`, `on: {'': ...}` → `always:` (0.4.0)
- Actor system: every actor belongs to a system, accessible via `system.get(id)` (0.5.0)

The algorithm core (SCXML microstep/macrostep) is shared between v4 and v5. Do not
replace `algorithm.py` — evolve it.

---

## Comparison context

| Library | Stars | Differentiator |
|---------|-------|----------------|
| `transitions` | ~6,500 | Most popular; broad but not SCXML-compliant |
| `python-statemachine` | ~1,200 | W3C SCXML test suite; strong statechart features |
| `xstate-statemachine` (basiltt) | ~14 | XState JSON compatible; active |
| `Sismic` | ~163 | Design by Contract; formal verification |
| `xstate` (this) | 194 | **XState JSON native; SCXML algorithm core** |

Our bet: own native XState JSON compatibility + SCXML algorithm correctness.
Ship a `SKILL.md` with the library once 0.1.0 API is stable (agensi.io-compatible).

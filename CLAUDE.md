# xstate-python — Project Context for AI Agents

## What this is

A Python implementation of [XState](https://github.com/statelyai/xstate) — statecharts and
hierarchical state machines for Python, following the W3C SCXML execution algorithm. The goal is
a **solid, published Python statechart library** that tracks XState v5's architecture and owns
the niche of native XState JSON compatibility.

**PyPI name:** `xstate` | **License:** MIT | **Python:** 3.9–3.13

---

## Architecture

```
xstate/
  __init__.py       Public API: `from xstate import Machine`
  machine.py        Machine class — entry point, orchestrates a statechart definition
  state_node.py     StateNode — represents a single state in the hierarchy
  state.py          State — current snapshot: {value, configuration, context, actions}
  algorithm.py      SCXML execution engine (microstep/macrostep, entry/exit sets)
  transition.py     Transition — event, guard, target, actions
  action.py         Action — entry/exit/transition side effects
  event.py          Event — typed event wrapper
  interpreter.py    Interpreter — synchronous event loop + queue, subscriptions, `after` scheduling
  scheduler.py      Clock abstractions (`SimulatedClock` for tests, `ThreadClock` for real time)
  scxml.py          SCXML XML → Machine config converter (requires `scxml` extra for js conds)
```

`algorithm.py` is the heart of the library. It implements the W3C SCXML algorithm:
`compute_entry_set`, `enter_states`, `exit_states`, `microstep`, `main_event_loop`.
The critical execution order is: `main_event_loop` → `microstep` → `main_event_loop2`
(which handles eventless transitions / `always` blocks after each macrostep).

---

## Current state (0.3.0 in progress)

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
- SCXML XML import (requires `pip install xstate[scxml]` for JS-cond evaluation)

**Stubbed / incomplete:**
- Async support (0.5.0 target)
- `setup()` API + XState v5 handler signatures (0.4.0+ target)
- Invoked services / actors (`invoke`) (0.5.0 target)

Handler-signature note: guards/assigners are invoked arity-aware (`()`,
`(context)`, or `(context, event)`) by `algorithm._invoke`. The XState v5
single-object signature `({context, event})` is a 0.4.0 target.

---

## Release roadmap

| Version | Theme | Key deliverables |
|---------|-------|-----------------|
| 0.1.0 | Capture & stabilize | Engine bug fixes, drop Js2Py hard dep, modern packaging, PyPI publish |
| 0.2.0 | Solid v4 FSM | Guards/conditions (pure Python), deep history, context/assign, full parallel |
| 0.3.0 | Interpreter | Synchronous event loop + queue, delayed transitions (`after`/`cancel`) |
| 0.4.0 | v5 config alignment | Rename `cond`→`guard`, `data`→`output`, `always:`, single-object handler signatures, MachineSnapshot |
| 0.5.0 | Actor model | `create_actor`, actor system, `from_promise`/`from_callback`, asyncio |
| 0.6.0+ | Setup & parity | `setup()`, composable guards, persistence, XState JSON from Stately.ai |

The differentiating niche: **XState / Stately.ai JSON compatibility** — neither `transitions`
nor `python-statemachine` accepts XState JSON natively.

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
mypy xstate/

# Format + lint
black xstate/ tests/
isort xstate/ tests/
flake8 xstate/ tests/
```

---

## Key constraints and guardrails

### Never reintroduce Js2Py as a hard dependency

`Js2Py` cannot build on Python 3.11+ and is a security anti-pattern for a library.
It has been moved to the optional `scxml` extra, lazy-imported inside `_eval_scxml_cond()`.
**Do not `import js2py` at module level anywhere in `xstate/`.**

The long-term plan (0.2.0) is to replace the remaining Js2Py usage in `scxml.py` with
a pure-Python SCXML condition evaluator.

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

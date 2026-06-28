# xstate-python - Project Context For AI Agents

## What This Is

`xstate-python` is a Python implementation of XState-style statecharts and
actor-based state machines. The project goal is to own the Python niche of
native XState / Stately JSON compatibility while preserving a W3C SCXML-style
run-to-completion execution core.

- PyPI name: `xstate`
- License: MIT
- Python: 3.13+
- Runtime dependencies: none
- Current status: alpha, version `0.6.0`

The central bet is simple: charts designed in Stately or shared with a
JavaScript frontend should load directly as Python `dict` / JSON data, with
Python supplying only live implementations such as actions, guards, delays, and
actor logic.

## Architecture Map

```text
src/xstate/
  __init__.py           Public exports
  machine.py            Machine entry point and pure transition API
  config_parser.py      Two-pass XState config parser and normalizer
  schema.py             TypedDict boundary for raw XState config data
  state_node.py         Resolved state hierarchy model
  transition.py         Resolved transition model
  state.py              Immutable public state snapshots / MachineSnapshot
  algorithm.py          SCXML microstep/macrostep execution algorithm
  action.py             Action constructors and interpreter-owned action types
  event.py              Event wrapper and conversion helpers
  exceptions.py         Custom exception classes
  handlers.py           HandlerArgs and HandlerAdapter callable adaptation
  context.py            ContextAdapter policies, including dataclass contexts
  interpreter.py        Synchronous runtime, queue, subscriptions, timers
  async_interpreter.py  Asyncio runtime and awaitable action execution
  actor.py              Actor system, create_actor, invoke reconciliation
  scheduler.py          Clock abstractions
  scxml.py              SCXML XML to Machine config converter
  setup_api.py          setup(...).create_machine(...) strict API
```

`algorithm.py` is the behavioral core. It implements the SCXML-inspired
entry/exit set, microstep, macrostep, internal queue, history, and eventless
transition flow. Treat it as correctness-critical.

## Current Capabilities

Working:

- Hierarchical, compound, parallel, final, and history states.
- Entry, exit, transition actions, `assign`, `raise_`, `send`, `cancel`,
  `send_parent`, and `send_to`.
- Guards with canonical XState v5 `guard`; legacy `cond` remains compatible and
  emits deprecation warnings where appropriate.
- `always`, `onDone`, `after`, delayed sends, named delays, and invoke
  lifecycle events.
- Pure `Machine.transition(state, event)` API.
- Sync `interpret(machine)` runtime with run-to-completion queueing,
  subscriptions, delayed transitions, and a thread-safe mutation boundary.
- Async `interpret_async(machine)` runtime with `await start/send/stop`, async
  actions, event-loop timers, and per-event completion for concurrent sends.
- Actor model: `create_actor`, `ActorSystem`, `spawn`, `from_promise`,
  `from_callback`, `from_observable`, and `to_promise`.
- XState v5 alignment: `guard`, `output`, `always`, `MachineSnapshot`,
  `state.matches(...)`, `state.can(...)`, and `setup(...).create_machine(...)`.
- XState snapshot queries: `tags`, `meta`, `state.has_tag(...)`,
  `state.hasTag(...)`, `state_in(...)`, and `stateIn(...)` are present on the
  0.7.0 branch.
- Dependency-free Mermaid diagram export via `to_mermaid(machine)` is present
  on the 0.7.0 branch.
- Handler adaptation through `HandlerArgs`, with legacy callable forms still
  supported at the public `Machine(config, ...)` boundary.
- Public snapshot immutability: configuration is a `frozenset`, actions are a
  `tuple`, and history is exposed read-only.
- SCXML import with a safe Python boolean condition subset:
  `true`, `false`, `!`, `&&`, `||`, and parentheses.

Known gaps:

- Full SCXML conformance still has known `more-parallel` failures.
- Graph/test helper APIs beyond Mermaid export are future work.
- SCXML condition support is intentionally not a general JavaScript evaluator.

## Important Constraints

### Preserve The Public Boundary

The main public entry point remains:

```python
from xstate import Machine

machine = Machine(config, actions={}, guards={}, delays={}, actors={})
state = machine.initial_state
state = machine.transition(state, "EVENT")
```

Do not break `Machine(config, ...)` XState JSON compatibility unless the user
explicitly asks for a breaking-change migration.

### Keep JavaScript Evaluation Out

Do not reintroduce Js2Py or any general JavaScript evaluator. The current SCXML
condition support is deliberately a small safe boolean parser. Unsupported
datamodel or JavaScript expressions should fail clearly with `InvalidConfigError`.

### Protect Run-To-Completion Semantics

Any change to `algorithm.py`, transition selection, interpreter queueing, timers,
history, or eventless transitions must preserve SCXML run-to-completion order.
When changing these areas, run the primary suite and the relevant SCXML tests.

### Respect Snapshot Immutability

Public `State` / `MachineSnapshot` containers are intentionally immutable at the
boundary. Keep mutable sets, lists, and dictionaries inside parser/algorithm
internals unless a public API explicitly requires otherwise.

### Keep Handler Adaptation Off The Hot Path

Prefer parse/setup-time `HandlerAdapter` adaptation. `algorithm._invoke` remains
only as a compatibility shim for opaque callables.

## Development Commands

```bash
# Install dev dependencies
poetry install

# Primary suite
poetry run python -m pytest tests/ --ignore=tests/test_scxml.py

# SCXML tests
git submodule update --init
poetry run python -m pytest tests/test_scxml.py

# Focused SCXML boolean cond subset
poetry run python -m pytest tests/test_scxml.py -k cond-js

# Type checking
poetry run mypy src/xstate/

# Format and lint
poetry run ruff format --check src/ tests/
poetry run ruff check src/ tests/
```

## PR And Branch Guidance

- Use descriptive branch names without a `codex/` prefix unless the user asks
  for that prefix.
- Keep PRs small and layered when possible.
- Prefer draft PRs for work that still needs review.
- Do not stage unrelated local files.
- If `AGENTS.md` is present and changes are requested, verify it against
  `pyproject.toml`, `README.md`, and the current merged `master` state before
  committing.

## Upstream And Positioning

```text
origin   -> JovaniPink/xstate-python
upstream -> statelyai/xstate-python
```

The upstream project is historically useful but mostly dormant. The active
direction here is Python 3.13+, XState v5 alignment, actor/runtime parity, and
native XState / Stately JSON compatibility.

Do not replace the SCXML algorithm core wholesale. Evolve it carefully.

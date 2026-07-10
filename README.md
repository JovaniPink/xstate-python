<h1 align="center">XState for Python</h1>

<p align="center">
  <strong>Statecharts and actor-based state machines for Python</strong>, shaped around
  <a href="https://github.com/statelyai/xstate">XState</a> configs and the
  <a href="https://www.w3.org/TR/scxml/#AlgorithmforSCXMLInterpretation">W3C SCXML</a>
  execution algorithm.
</p>

<p align="center">
  <a href="https://github.com/JovaniPink/xstate-python/actions/workflows/pull_request.yaml"><img alt="Tests and code quality" src="https://github.com/JovaniPink/xstate-python/actions/workflows/pull_request.yaml/badge.svg"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.13%2B-blue">
  <img alt="Status" src="https://img.shields.io/badge/status-alpha%20(0.7.0)-orange">
  <a href="./LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-green"></a>
</p>

---

## Why This Library?

This project has a narrow, useful goal: load native
[XState](https://github.com/statelyai/xstate) / [Stately](https://stately.ai/editor)
JSON in Python and run it with a statechart engine that follows the SCXML
microstep/macrostep model.

That means a chart designed visually in Stately, or shared with a JavaScript
frontend, can stay declarative:

```python
import json

from xstate import Machine

with open("machine.json") as f:
    config = json.load(f)

machine = Machine(config)
```

Only live implementation details need Python bindings: action functions, guard
functions, delay values, and actor logic.

| | xstate-python |
|---|---|
| XState JSON | Loaded directly as Python `dict` data |
| Engine | W3C SCXML-style run-to-completion algorithm |
| Core runtime deps | None |
| Main runtime APIs | Pure `Machine.transition`, `Interpreter`, `AsyncInterpreter`, `Actor` |
| Current focus | XState v5 alignment, actors, setup, and SCXML correctness |

## Installation

Install the released package from PyPI:

```bash
pip install xstate
```

For an unreleased checkout, install from source:

```bash
git clone https://github.com/JovaniPink/xstate-python.git
cd xstate-python
poetry install
```

The core library has no runtime dependencies. The `scxml` extra is intentionally
dependency-free on Python 3.13+; SCXML Boolean `cond` support covers the safe
subset `true`, `false`, `!`, `&&`, `||`, and parentheses.

## Quickstart

`Machine` is the pure state transition layer: `(state, event) -> state`.

```python
from xstate import Machine

lights = Machine(
    {
        "id": "lights",
        "initial": "green",
        "states": {
            "green": {"on": {"TIMER": "yellow"}},
            "yellow": {"on": {"TIMER": "red"}},
            "red": {"on": {"TIMER": "green"}},
        },
    }
)

state = lights.initial_state
assert state.value == "green"

state = lights.transition(state, "TIMER")
assert state.value == "yellow"
```

Use an event object when you need payload data:

```python
state = lights.transition(state, {"type": "TIMER", "source": "clock"})
```

## Loading XState JSON

The JSON stays data-only. Python registries provide implementations by name:

```python
import json

from xstate import Machine, assign, from_promise

with open("search_machine.json") as f:
    config = json.load(f)

machine = Machine(
    config,
    guards={"hasQuery": lambda ctx, event: bool(event.data.get("query"))},
    actions={"rememberQuery": assign({"query": lambda _ctx, event: event.data["query"]})},
    delays={"debounce": 300},
    actors={"fetchResults": from_promise(lambda input: ["Ada", "Grace"])},
)
```

Prefer XState v5 keys such as `guard`, `output`, and `always`. Older `cond`,
`data`, and `on: {"": ...}` forms remain supported for compatibility and may
emit deprecation warnings.

## Running A Machine

`interpret(machine)` turns a pure machine into a stateful service with
subscriptions, run-to-completion queuing, delayed transitions, and side-effect
actions:

```python
from xstate import interpret

service = interpret(machine).start()
subscription = service.subscribe(lambda state: print("->", state.value))

service.send("SEARCH")
subscription.unsubscribe()
service.stop()
```

Delayed transitions use a pluggable clock. Use `SimulatedClock` in tests:

```python
from xstate import Machine, interpret
from xstate.scheduler import SimulatedClock

machine = Machine(
    {
        "id": "timer",
        "initial": "waiting",
        "states": {
            "waiting": {"after": {1000: "done"}},
            "done": {"type": "final"},
        },
    }
)

clock = SimulatedClock()
service = interpret(machine, clock=clock).start()

clock.increment(1000)
assert service.state.value == "done"
```

The synchronous interpreter serializes timer callbacks and user sends with a
re-entrant lock so `ThreadClock` callbacks cannot interleave state mutation.

## Async Runtime

`interpret_async(machine)` provides the asyncio-native runtime. It supports
`await start()`, `await send()`, `await stop()`, async action callables, and
event-loop scheduled `after` transitions:

```python
from xstate import interpret_async

service = interpret_async(machine)
await service.start()
await service.send("SEARCH")
await service.stop()
```

The pure transition and guard layer remains synchronous; only action execution,
timers, and actor settlement are async-aware.

## Actors And `invoke`

XState v5 treats running logic as actors. This library supports machine actors,
promise actors, callback actors, observable actors, spawning, parent/child
messaging, and `invoke` lifecycle wiring.

```python
from xstate import Machine, assign, create_actor, from_promise


def fetch_user(input):
    return {"id": input["user_id"], "name": "Ada"}


machine = Machine(
    {
        "id": "fetcher",
        "context": {"user_id": 42, "user": None},
        "initial": "loading",
        "states": {
            "loading": {
                "invoke": {
                    "id": "getUser",
                    "src": "fetchUser",
                    "input": lambda ctx, _event: {"user_id": ctx["user_id"]},
                    "onDone": {
                        "target": "success",
                        "actions": [assign({"user": lambda _ctx, event: event.data})],
                    },
                    "onError": "failure",
                }
            },
            "success": {"type": "final"},
            "failure": {},
        },
    },
    actors={"fetchUser": from_promise(fetch_user)},
)

actor = create_actor(machine).start()
snapshot = actor.get_snapshot()

assert snapshot.value == "success"
assert snapshot.context["user"]["name"] == "Ada"
```

Actor helpers exported from `xstate` include:

- `create_actor(machine_or_logic)`
- `from_promise(fn)`
- `from_callback(fn)`
- `from_observable(fn_or_async_iterable)`
- `to_promise(actor)`
- `send_parent(event)` and `send_to(actor_id, event)`

## `setup()` And Handler Signatures

`setup(...)` mirrors XState v5's named implementation style and creates machines
in stricter mode:

```python
from xstate import HandlerArgs, setup


def has_query(args: HandlerArgs) -> bool:
    return bool(args.event.data.get("query"))


machine = setup(guards={"hasQuery": has_query}).create_machine(
    {
        "id": "search",
        "initial": "idle",
        "states": {
            "idle": {"on": {"SEARCH": {"target": "searching", "guard": "hasQuery"}}},
            "searching": {},
        },
    }
)
```

Legacy callables still work through adapter compatibility: `()`, `(context)`,
`(context, event)`, and keyword-only `(*, context, event)`.

## Context And Snapshots

`context` is extended state. Use `assign(...)` to return updated context during
a transition:

```python
from xstate import Machine, assign

counter = Machine(
    {
        "id": "counter",
        "context": {"count": 0},
        "initial": "active",
        "states": {
            "active": {
                "on": {
                    "INC": {
                        "actions": [
                            assign({"count": lambda ctx, _event: ctx["count"] + 1})
                        ]
                    }
                }
            }
        },
    }
)
```

By default, state context is snapshot-isolated with deep copies. Public snapshot
containers are immutable at the boundary: `configuration` is a `frozenset`,
`actions` is a `tuple`, and `history_value` is read-only. For immutable
dataclass contexts, use `dataclass_context()` / `DataclassContextAdapter`.

Snapshots also expose XState-style query data:

```python
state = machine.initial_state

state.has_tag("loading")  # Pythonic
state.hasTag("loading")   # XState-compatible alias
state.tags                # frozenset of active state tags
state.meta                # read-only mapping of active state ids to metadata
```

Use `state_in(...)` / `stateIn(...)` when a reusable guard should depend on the
current active state configuration:

```python
from xstate import Machine, state_in

machine = Machine(
    {
        "id": "workflow",
        "initial": "editing",
        "states": {
            "editing": {"on": {"SUBMIT": "review"}},
            "review": {
                "on": {
                    "APPROVE": {
                        "target": "published",
                        "guard": state_in("review"),
                    }
                }
            },
            "published": {"type": "final", "tags": ["done"]},
        },
    }
)
```

## Core Statechart Features

- Hierarchical and parallel states
- State tags, metadata, `matches(...)`, `can(...)`, and `has_tag(...)`
- Entry, exit, and transition actions
- Named and inline guards
- Context and `assign`
- Higher-order actions with `choose(...)` and `pure(...)`
- Eventless transitions via `always`
- Final states and `onDone`
- Shallow and deep history states
- Delayed transitions via `after`
- SCXML XML import
- Actor invocation with `invoke`, `onDone`, and `onError`

## Diagrams

`to_mermaid(machine)` exports a dependency-free Mermaid `stateDiagram-v2` string:

```python
from xstate import to_mermaid

print(to_mermaid(machine))
```

This is intentionally lightweight: it covers state hierarchy, initial states,
transition arrows, and targetless-transition comments without adding Graphviz or
browser-rendering dependencies.

## Examples

Runnable examples live in [`docs/examples/`](./docs/examples):

| Example | Showcases |
|---|---|
| [`traffic_intersection.json`](./docs/examples/traffic_intersection.json) + [`traffic_intersection.py`](./docs/examples/traffic_intersection.py) | XState JSON loading, parallel regions, nested states, named delays, guards, entry actions, and deterministic clocks |
| [`fetch_with_retry.py`](./docs/examples/fetch_with_retry.py) | `invoke`, `from_promise`, retries with `after`, context assignment, and guarded transitions |

Run them from the repo root:

```bash
PYTHONPATH=src python3 docs/examples/traffic_intersection.py
PYTHONPATH=src python3 docs/examples/fetch_with_retry.py
```

## Public API

```python
from xstate import (
    Machine,
    MachineSnapshot,
    setup,
    HandlerArgs,
    interpret,
    interpret_async,
    create_actor,
    from_promise,
    from_callback,
    from_observable,
    to_promise,
    assign,
    send,
    send_parent,
    send_to,
    cancel,
    raise_,
    choose,
    pure,
    state_in,
    stateIn,
    to_mermaid,
    dataclass_context,
)
from xstate.scheduler import SimulatedClock, ThreadClock
```

## SCXML

The algorithm core follows the W3C SCXML execution model. XML import is exposed
through `xstate.scxml.scxml_to_machine(...)` and verified against the SCXML test
framework:

```bash
git submodule update --init
poetry run python -m pytest tests/test_scxml.py
```

Current branch result: `45 passed`, `8 failed`; the remaining failures are the
known `more-parallel` conformance cases. The `cond-js` subset passes with the
safe Boolean evaluator.

## Developing

```bash
poetry install

# Primary suite
poetry run python -m pytest tests/ --ignore=tests/test_scxml.py

# Type checking
poetry run mypy src/xstate/

# Formatting and linting
poetry run ruff format --check src/ tests/
poetry run ruff check src/ tests/
```

### Release preflight

Before creating the GitHub Release for `0.7.0`, run the local preflight from
the target commit:

```bash
poetry run python scripts/release_preflight.py v0.7.0
```

The preflight verifies the expected tag against `pyproject.toml`, checks that
`HEAD` matches `origin/master`, runs the release quality gates, and builds the
distribution without publishing. Pass `--target-ref` or `--master-ref` if the
release target needs to be checked against different refs.

## Roadmap

| Area | Current state |
|---|---|
| PyPI release | `0.7.0` release-readiness is complete; publish via GitHub Release |
| XState v5 setup | `setup(...).create_machine(...)` and composable guards are present |
| Snapshot queries | `tags`, `meta`, `has_tag`/`hasTag`, and `state_in`/`stateIn` are present |
| Diagrams | Dependency-free Mermaid export is present |
| Async | `AsyncInterpreter`, async actors, `from_observable`, and `to_promise` are present |
| SCXML | XML import works; safe Boolean cond subset works; `more-parallel` conformance remains open |
| Persistence | Snapshot serialization and restore helpers are present |

## Related Projects

- [XState](https://github.com/statelyai/xstate)
- [Stately](https://stately.ai/editor)
- [python-statemachine](https://github.com/fgmacedo/python-statemachine)
- [transitions](https://github.com/pytransitions/transitions)
- [Sismic](https://github.com/AlexandreDecan/sismic)

## License

[MIT](./LICENSE)

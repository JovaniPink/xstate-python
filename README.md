<h1 align="center">XState for Python</h1>

<p align="center">
  <strong>Statecharts and state machines for Python</strong> — a port of
  <a href="https://github.com/statelyai/xstate">XState</a> built on the
  <a href="https://www.w3.org/TR/scxml/#AlgorithmforSCXMLInterpretation">W3C SCXML</a>
  execution algorithm.
</p>

<p align="center">
  <a href="https://github.com/JovaniPink/xstate-python/actions"><img alt="Tests" src="https://img.shields.io/badge/tests-194%20passing-brightgreen"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.9%20%E2%80%93%203.13-blue">
  <img alt="Status" src="https://img.shields.io/badge/status-alpha%20(0.5.0)-orange">
  <a href="./LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-green"></a>
</p>

---

## Why this library?

There are several good Python state-machine libraries. This one owns a specific
niche: **native [XState](https://github.com/statelyai/xstate) / [Stately.ai](https://stately.ai/editor)
JSON compatibility, backed by a real SCXML execution engine.**

A statechart you design in the Stately editor or share with a JavaScript
codebase is the *same* JSON you load here — no translation layer:

```python
import json
from xstate import Machine

machine = Machine(json.load(open("my_machine.json")))
```

| | xstate-python |
|---|---|
| **XState JSON** | Loaded directly as a Python `dict` — the differentiator |
| **Engine** | W3C SCXML microstep/macrostep algorithm (`algorithm.py`) |
| **Statechart features** | Hierarchy, parallel regions, history, guards, context, delays, actors |
| **Runtime** | Pure `Machine.transition` *or* a stateful `Interpreter` / `Actor` |
| **Dependencies** | **None** for the core (SCXML XML import is an optional extra) |

See [`docs/comparison.md`](./docs/comparison.md) for a full feature matrix against
`transitions`, `python-statemachine`, `Sismic`, and others.

## Installation

```bash
# from source (no PyPI release yet — 0.5.0 in progress)
git clone https://github.com/JovaniPink/xstate-python.git
cd xstate-python
poetry install
```

The core has **no runtime dependencies**. SCXML *XML* import (with JavaScript
`cond` evaluation) is an optional extra: `pip install "xstate[scxml]"`.

## Quickstart

A `Machine` is a pure function over `(state, event) -> state`:

```python
from xstate import Machine

lights = Machine({
    "id": "lights",
    "initial": "green",
    "states": {
        "green":  {"on": {"TIMER": "yellow"}},
        "yellow": {"on": {"TIMER": "red"}},
        "red":    {"on": {"TIMER": "green"}},
    },
})

state = lights.initial_state          # state.value == "green"
state = lights.transition(state, "TIMER")   # "yellow"
state = lights.transition(state, "TIMER")   # "red"
```

`machine.transition` has no side effects — it returns a fresh `State`. To run a
machine as a live, stateful service with an event queue, use the
[`Interpreter`](#running-a-machine--interpreter) or
[`Actor`](#actors--invoke-050) APIs below.

## Core concepts

### Hierarchical (compound) states

States can nest. A `final` child fires `onDone` on its parent:

```python
machine = Machine({
    "id": "lights",
    "initial": "green",
    "states": {
        "green":  {"on": {"TIMER": "yellow"}},
        "yellow": {"on": {"TIMER": "red"}},
        "red": {
            "initial": "walk",
            "states": {
                "walk":    {"on": {"COUNTDOWN": "wait"}},
                "wait":    {"on": {"COUNTDOWN": "stop"}},
                "stop":    {"on": {"TIMEOUT": "timeout"}},
                "timeout": {"type": "final"},
            },
            "onDone": "green",
        },
    },
})
# state.value for a compound state is a dict: {"red": "walk"}
```

### Parallel states

A `parallel` state activates all of its regions at once; events broadcast to
every region. `value` becomes a nested dict:

```python
player = Machine({
    "id": "player",
    "type": "parallel",
    "states": {
        "playback": {
            "initial": "paused",
            "states": {
                "paused":  {"on": {"PLAY": "playing"}},
                "playing": {"on": {"PAUSE": "paused"}},
            },
        },
        "volume": {
            "initial": "unmuted",
            "states": {
                "unmuted": {"on": {"MUTE": "muted"}},
                "muted":   {"on": {"UNMUTE": "unmuted"}},
            },
        },
    },
})
# state.value == {"playback": "paused", "volume": "unmuted"}
```

### Guards (conditions)

A transition only fires if its `cond` passes. Guards are a callable
`(context, event) -> bool`, or a string resolved from the `guards=` registry:

```python
machine = Machine(
    {
        "id": "search",
        "initial": "idle",
        "states": {
            "idle": {
                "on": {
                    "SEARCH": {"target": "searching", "cond": "isNotEmpty"},
                },
            },
            "searching": {},
        },
    },
    guards={"isNotEmpty": lambda ctx, ev: bool(ev.data.get("query"))},
)
```

### Context and `assign`

`context` is the machine's extended (quantitative) state. Update it with the
`assign` action — snapshots are deep-copied, so transitions never mutate a prior
state:

```python
from xstate import Machine, assign

counter = Machine({
    "id": "counter",
    "context": {"count": 0},
    "initial": "active",
    "states": {
        "active": {
            "on": {
                "INC": {"actions": [assign({"count": lambda c, e: c["count"] + 1})]},
                "RESET": {"actions": [assign({"count": 0})]},
            },
        },
    },
})

# Event payloads reach guards/assigners via event.data:
state = counter.transition(counter.initial_state, {"type": "INC"})
state.context  # {"count": 1}
```

### Entry / exit actions

Run side effects on entering or leaving a state. Reference them by name and
supply implementations through `actions=`:

```python
machine = Machine(
    {
        "id": "door",
        "initial": "closed",
        "states": {
            "closed": {"entry": ["lock"], "exit": ["unlock"], "on": {"OPEN": "open"}},
            "open": {},
        },
    },
    actions={"lock": lambda: print("locked"), "unlock": lambda: print("unlocked")},
)
```

### History states

A history pseudo-state restores a parent's most recent configuration —
`shallow` (default) or `deep`:

```python
"hist": {"type": "history", "history": "deep"}
```

### Eventless transitions (`always`)

Transitions that are checked immediately after every step, taken as soon as
their guard passes (XState v5 `always:`; the v4 `on: {"": ...}` form also works):

```python
"checking": {
    "always": [
        {"target": "valid", "cond": "isValid"},
        {"target": "invalid"},
    ],
},
```

## Running a machine — `Interpreter`

The `Interpreter` turns a pure machine into a live service with a
run-to-completion event queue, subscriptions, and delayed transitions:

```python
from xstate import Machine, interpret

service = interpret(machine).start()
service.subscribe(lambda state: print("->", state.value))
service.send("TIMER")
service.stop()
```

### Delayed transitions (`after`)

`after` schedules a transition some milliseconds after a state is entered, and
cancels it on exit. Timing runs through a pluggable **`Clock`**:

```python
from xstate import Machine, interpret
from xstate.scheduler import SimulatedClock

machine = Machine(
    {
        "id": "light",
        "initial": "green",
        "states": {
            "green":  {"after": {"GREEN_TIME": "yellow"}},
            "yellow": {"after": {2000: "red"}},
            "red":    {},
        },
    },
    delays={"GREEN_TIME": 6000},   # named delays resolve here
)

clock = SimulatedClock()           # deterministic — no real waiting
service = interpret(machine, clock=clock).start()
clock.increment(6000)              # fires green -> yellow
clock.increment(2000)              # fires yellow -> red
```

Use `SimulatedClock` in tests for reproducible timing; `ThreadClock` (the
default) uses real wall-clock time.

## Actors & `invoke` (0.5.0)

The actor model is XState v5's runtime. `create_actor` runs *actor logic* — a
`Machine`, or logic from `from_promise` / `from_callback` — as an addressable
actor inside a system.

### `invoke:` — run a child actor for a state's lifetime

```python
from xstate import Machine, assign, create_actor, from_promise

def fetch_user(input):
    return {"id": input["user_id"], "name": "Ada"}

machine = Machine(
    {
        "id": "fetcher",
        "initial": "loading",
        "context": {"user_id": 42, "data": None},
        "states": {
            "loading": {
                "invoke": {
                    "id": "getUser",
                    "src": "fetchUser",
                    "input": lambda ctx, ev: {"user_id": ctx["user_id"]},
                    "onDone": {
                        "target": "done",
                        "actions": [assign({"data": lambda c, e: e.data})],
                    },
                    "onError": "failed",
                },
            },
            "done": {"type": "final"},
            "failed": {},
        },
    },
    actors={"fetchUser": from_promise(fetch_user)},
)

actor = create_actor(machine).start()
actor.get_snapshot().value      # "done"
actor.get_snapshot().context    # {"user_id": 42, "data": {"id": 42, "name": "Ada"}}
```

### Actor logic kinds

- **`from_promise(fn)`** — `fn(input)` runs once; resolves to `done.invoke.<id>`
  (`onDone`) or, if it raises, `error.platform.<id>` (`onError`).
- **`from_callback(fn)`** — `fn(send_back, receive, input)` bridges an external
  event source; `send_back(event)` notifies the parent, `receive(handler)`
  handles incoming events, and a returned callable runs as cleanup on stop.

### Spawning and messaging

```python
child = actor.spawn(child_machine, id="worker")   # ad-hoc child actor

from xstate import send_parent, send_to
# inside a child machine:  {"entry": [send_parent("READY")]}
# address a sibling by id: {"actions": [send_to("logger", "LOG")]}
```

## Loading from XState JSON

Because the config *is* XState JSON, the structure lives in a `.json` file and
only the live parts (guards, actions, delays, actor logic) are wired in Python,
keyed by the names used in the JSON:

```python
import json
from xstate import Machine

config = json.load(open("machine.json"))
machine = Machine(
    config,
    guards={"crossingIsClear": ...},
    actions={"allRed": ...},
    delays={"walkTime": 5000},
    actors={"fetchUser": ...},
)
```

> **Note:** `assign` carries a live callable, so context mutations are written
> in Python rather than in the JSON. Everything else — hierarchy, parallel
> regions, guards/actions/delays/actor logic *by name*, `after`, `onDone` —
> is fully declarative.

## Examples

Runnable, verified examples live in [`docs/examples/`](./docs/examples):

| Example | Showcases |
|---|---|
| [`traffic_intersection.json`](./docs/examples/traffic_intersection.json) + [`.py`](./docs/examples/traffic_intersection.py) | A complex chart **loaded from JSON**: parallel regions, nested compound states, named `after` delays, a guarded pedestrian request, and a global `EMERGENCY` override |
| [`fetch_with_retry.py`](./docs/examples/fetch_with_retry.py) | The **0.5.0 actor model**: `invoke` + `from_promise`, `onDone`/`onError`, context/`assign`, a `canRetry` guard, and `after` backoff |

```bash
PYTHONPATH=. python docs/examples/traffic_intersection.py
PYTHONPATH=. python docs/examples/fetch_with_retry.py
```

Smaller snippets are in [`examples/`](./examples).

## Public API

```python
from xstate import (
    Machine,                       # pure (state, event) -> state
    interpret, Interpreter,        # running service + event queue
    create_actor, Actor, ActorSystem,   # actor model (v5)
    from_promise, from_callback,   # actor logic kinds
    assign, send, send_parent, send_to, cancel, raise_,   # action creators
    MachineSnapshot,               # v5 snapshot
)
from xstate.scheduler import Clock, SimulatedClock, ThreadClock
```

```python
machine = Machine(config, actions={}, guards={}, delays={}, actors={})
state = machine.initial_state          # State(value, configuration, context, actions)
state = machine.transition(state, "EVENT" | {"type": "EVENT", ...})
state.value      # str for atomic states, dict for compound/parallel
state.context    # extended state
state.can(event) # bool — would this event cause a transition?
```

## Roadmap

| Version | Theme | Highlights |
|---|---|---|
| 0.1.0 | Stabilize | Engine fixes, drop Js2Py hard dep, modern packaging |
| 0.2.0 | Solid v4 FSM | Pure-Python guards, deep history, context/`assign`, full parallel |
| 0.3.0 | Interpreter | RTC event loop, delayed transitions (`after`/`cancel`) |
| 0.4.0 | v5 alignment | `guard`/`output`/`always:`, single-object handlers, `MachineSnapshot` |
| **0.5.0** | **Actor model** | **`create_actor`, `invoke`, `from_promise`/`from_callback`, messaging** ← current |
| 0.6.0+ | Setup & parity | `setup()`, composable guards, persistence, asyncio |

## SCXML

The engine implements the [W3C SCXML algorithm](https://www.w3.org/TR/scxml/#AlgorithmforSCXMLInterpretation).
SCXML *XML* documents can be imported with `pip install "xstate[scxml]"`, and the
[SCION test framework](./test-framework) (a git submodule) verifies conformance:

```bash
git submodule update --init
poetry run pytest tests/test_scxml.py
```

## Developing

```bash
poetry install                                   # dev deps
poetry run pytest --ignore=tests/test_scxml.py   # primary test suite (194 tests)
poetry run mypy xstate/                           # type check
poetry run black xstate/ tests/                   # format
poetry run isort xstate/ tests/
poetry run flake8 xstate/ tests/
```

A VS Code [dev container](https://code.visualstudio.com/docs/remote/containers)
is included: open the folder in a container and run the tests.

## Related projects

- [XState](https://github.com/statelyai/xstate) — the original JavaScript/TypeScript library
- [Stately.ai](https://stately.ai/editor) — visual statechart editor (exports the JSON this library loads)
- [python-statemachine](https://github.com/fgmacedo/python-statemachine) · [transitions](https://github.com/pytransitions/transitions) · [Sismic](https://github.com/AlexandreDecan/sismic)

## License

[MIT](./LICENSE)

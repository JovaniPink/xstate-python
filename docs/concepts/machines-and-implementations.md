# Machines And Implementations

The primary compatibility boundary is a plain XState-style configuration:

```python
from xstate import Machine

machine = Machine(
    {
        "id": "approval",
        "initial": "draft",
        "states": {
            "draft": {"on": {"SUBMIT": "review"}},
            "review": {"on": {"APPROVE": "approved"}},
            "approved": {"type": "final"},
        },
    }
)
```

The configuration can be authored as a Python dictionary or loaded from JSON.
State structure stays declarative; Python supplies implementations for names
that cannot be represented as data.

## Pure Transitions

`Machine.transition` is the pure statechart layer. It accepts an immutable
snapshot and an event, then returns the next snapshot:

```python
state = machine.initial_state
state = machine.transition(state, "SUBMIT")
assert state.value == "review"
```

An event can be a string or a mapping with a `type` and payload fields:

```python
state = machine.transition(
    state,
    {"type": "APPROVE", "reviewer_id": 42},
)
```

Assignments are applied while the next snapshot is computed. Side-effect
actions are returned on `state.actions`; use an interpreter or actor when those
actions should be executed automatically.

## Named Implementations

JSON refers to implementations by name. Register those names when constructing
the machine:

```python
from xstate import HandlerArgs, Machine, assign


def has_reviewer(args: HandlerArgs) -> bool:
    return bool(args.event.data.get("reviewer_id"))


machine = Machine(
    config,
    guards={"hasReviewer": has_reviewer},
    actions={
        "rememberReviewer": assign(
            {"reviewer_id": lambda _context, event: event.data["reviewer_id"]}
        )
    },
    delays={"reviewTimeout": 30_000},
    actors={"notifyReviewer": notification_actor_logic},
)
```

The registry names have distinct roles:

| Registry | Used for |
|---|---|
| `actions` | Side effects and built-in action creators such as `assign` |
| `guards` | Boolean transition conditions |
| `delays` | Millisecond values or functions used by named `after` transitions |
| `actors` | Actor logic referenced by `invoke.src` |

Missing named guards and delays raise an implementation error when they are
needed. Missing side-effect actions emit a warning at the compatibility
`Machine(config, ...)` boundary.

## `setup()` And Handler Arguments

`setup(...)` registers implementations before creating a machine and enables a
stricter XState v5-style authoring path:

```python
from xstate import setup

machine = setup(guards={"hasReviewer": has_reviewer}).create_machine(config)
```

Prefer a single `HandlerArgs` parameter for new handlers. It exposes `context`,
`event`, and implementation `params`. Legacy `()`, `(context)`, and
`(context, event)` callables remain supported by `Machine(config, ...)`.

## Context And Snapshots

Snapshots isolate context through the configured `ContextAdapter`. The default
adapter deep-copies context; `dataclass_context()` supports immutable dataclass
contexts. Public snapshot containers remain immutable: configuration is a
`frozenset`, actions are a tuple, and history values are read-only.

Use `state.matches(...)`, `state.can(...)`, `state.has_tag(...)`, and
`state.meta` to query a snapshot without reaching into algorithm internals.

## Complete Example

The [traffic intersection](../examples/traffic_intersection.py) loads its state
structure from [XState JSON](../examples/traffic_intersection.json), then binds
named actions, guards, and delays in Python.

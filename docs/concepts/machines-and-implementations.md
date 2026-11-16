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
actions should be executed automatically. Each action retains the arguments
captured at its position, even when later assignments change the returned
snapshot's context.

Once a snapshot is done, further `Machine.transition(snapshot, event)` calls
preserve its terminal value and output and return no actions. `state.can(event)`
returns `False`. The transition that first completes the machine includes exit
effects for the remaining active states, in reverse document order; the final
configuration remains available for inspection. See
[runtime completion](runtimes.md#final-completion) for resource cleanup.

## Re-entry And Migration

JSON transitions use XState-style `reenter: false` when neither `reenter` nor
the legacy `type` field is supplied. For a transition targeting its own state
or a descendant, the source state remains active. Descendants can still exit
and enter as the target requires. Resources owned by retained states remain
running; resources owned by states that actually exit are reconciled.

| Configuration | Transition policy |
|---|---|
| `reenter` omitted, `type` omitted | XState-style `reenter: false` |
| `"reenter": false` | Retain the source for self/descendant targets |
| `"reenter": true` | Exit and re-enter the source for self/descendant targets, resetting its timers and invoked children |
| Explicit `"type": "internal"` or `"type": "external"`, with no `reenter` | Preserve the legacy SCXML-style transition-domain rules |

An explicit `reenter` takes precedence over a valid legacy `type`. It must be
a Boolean: strings, numbers, and `null` raise `InvalidConfigError` with the
configuration path. A targetless transition still performs its actions without
exiting its source.

**Migration:** older JSON charts could rely on implicit external behavior for
self or descendant targets. Use `{"target": "active", "reenter": true}` when
a self-transition should reset that state. Use an explicit legacy
`"type": "external"` to preserve the earlier transition-domain policy.
SCXML import keeps its explicit or default external policy. Modern XState and
SCXML domain rules can differ in parallel charts; these migration choices are
not a claim that the two policies are equivalent.

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
| `delays` | Millisecond values or functions used by named `after` and send delays |
| `actors` | Actor logic referenced by `invoke.src` |

Missing named guards and delays raise an implementation error when they are
needed. Missing side-effect actions emit a warning at the compatibility
`Machine(config, ...)` boundary.

Numeric JSON `after` keys such as `"1000"` are milliseconds. They take
precedence over a same-named delay implementation; use a descriptive name such
as `"reviewTimeout"` when a registry controls the duration. String delays in
`send(..., delay="1000")` still refer to the registry. See the
[supported numeric grammar and migration notes](xstate-compatibility.md#numeric-after-keys).

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

### Action Arguments And Migration

Deferred actions capture their arguments while the machine computes the
transition. The same rule applies to named and inline handlers, entry and exit
actions, and actions expanded by `choose(...)` or `pure(...)`:

| Action argument | Meaning |
|---|---|
| `context` | `ContextAdapter.snapshot(context)` at this action's position, before any later assignment |
| `event` | The effective `Event` reference: `xstate.init` for initial entry, the triggering event for each microstep, and the current event carried into eventless transitions |
| `params` | The declared parameter value by reference; callable action parameters are passed through without evaluation |
| `state` | `None` for action handlers |

Actions returned by `pure` use the same normalization, named action/guard
registries, and context policy as configured actions, including nested `choose`
and `pure` results. Computing a transition or a microstep trace does not execute
deferred effects.

**Migration:** normal transition results previously bound handlers to the final
macrostep context and outer event. A handler before an assignment now sees the
earlier context; a handler caused by a raised event sees that internal event. Use `assign` to
update chart context. With the default adapter, mutating a handler's context
does not update the committed snapshot or another action's captured context.
Event payloads and parameters are not copied, so their mutable contents remain
shared with their owners.

Runtime snapshots are still committed before effects execute. Reading
`service.state` inside a handler therefore observes the completed macrostep,
which may differ from that handler's arguments. See the
[runtime guide](runtimes.md#action-arguments-and-committed-state).

## Context And Snapshots

Snapshots isolate context through the configured `ContextAdapter`. The default
adapter deep-copies context; `dataclass_context()` supports immutable dataclass
contexts. Public snapshot containers remain immutable: configuration is a
`frozenset`, actions are a tuple, and history values are read-only.

The same context policy captures each deferred action's context, independently
of whether tracing is enabled. Large mutable contexts and many deferred actions
therefore incur repeated deep copies with the default adapter. Measure this
cost on the application chart. `dataclass_context()` shares context without
copying and requires immutable values, including nested contents; custom
adapters define their own ownership and copying policy.

Use `state.matches(...)`, `state.can(...)`, `state.has_tag(...)`, and
`state.meta` to query a snapshot without reaching into algorithm internals.

## Complete Example

The [traffic intersection](../examples/traffic_intersection.py) loads its state
structure from [XState JSON](../examples/traffic_intersection.json), then binds
named actions, guards, and delays in Python.

The [docking controller](../examples/docking_controller.py) demonstrates bound
methods, typed event mappings, an immutable dataclass context, named phase
timeouts, and a typed application facade around a data-only JSON chart.
Its [integration guide](controllers.md) explains periodic control and replay.

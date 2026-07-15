# Examples

These examples are meant to be readable first and realistic second. Run them
from the repository root with `PYTHONPATH=src`:

```bash
PYTHONPATH=src python3 docs/examples/traffic_intersection.py
PYTHONPATH=src python3 docs/examples/fetch_with_retry.py
PYTHONPATH=src python3 docs/examples/async_workflow.py
```

## Traffic Intersection

Files: [`traffic_intersection.json`](./traffic_intersection.json) and
[`traffic_intersection.py`](./traffic_intersection.py)

This is the headline XState JSON example. The chart is stored as plain JSON,
matching the shape exported by Stately/XState tooling. Python supplies only the
live implementation details:

```python
with open("docs/examples/traffic_intersection.json") as f:
    config = json.load(f)

machine = Machine(config, actions=ACTIONS, guards=GUARDS, delays=DELAYS)
```

It models a road intersection with three parallel regions plus a global
emergency override:

```text
intersection
├── operational (parallel)
│   ├── northSouth: green -> yellow -> red
│   ├── eastWest:   red -> green -> yellow
│   └── pedestrian: dontWalk -> walk -> flashing
└── emergency
```

What to look for:

| Feature | Where |
|---|---|
| Parallel regions | `operational` activates traffic and pedestrian regions together |
| Nested states | each region has its own local chart |
| Named delays | JSON delay names resolve through `delays={...}` |
| Guards | `PED_REQUEST` checks `crossingIsClear` |
| Entry actions | `startWalkSignal` and `allRed` are supplied by name |
| Deterministic time | `SimulatedClock.increment(ms)` fires due timers |

## Fetch With Retry

File: [`fetch_with_retry.py`](./fetch_with_retry.py)

This example shows the actor model. A parent machine invokes a promise actor,
records success or failure in context, and retries with a delayed transition.

```text
idle --FETCH--> loading
loading invokes fetchUser
  onDone  -> success
  onError -> retrying
retrying --after backoff--> loading
retrying --always [exhausted]--> failure
```

What to look for:

| Feature | Where |
|---|---|
| `invoke` lifecycle | `loading.invoke` starts child logic while the state is active |
| Promise actor | `from_promise(fetch_user)` |
| Completion events | `onDone` / `onError` handle actor settlement |
| Context updates | `assign` records data, errors, and retries |
| Guards | `canRetry` and `exhausted` choose the retry path |
| Delayed retry | `after: {"backoff": ...}` |

This example is intentionally a Python dict because it contains live callables
for `input`, guards, actions, and the promise actor. Pure state structure can
still live in JSON when those live pieces are referenced by name.

## Async Workflow

File: [`async_workflow.py`](./async_workflow.py)

This compact asyncio example runs an awaitable action through
`interpret_async(machine)`. It shows awaitable lifecycle methods, synchronous
snapshot subscriptions, event payload access through `HandlerArgs`, and the
guarantee that `await send(...)` completes after that event's async actions.

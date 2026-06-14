# Examples

Two runnable, verified showcases of xstate-python. Run them from the repo root:

```bash
PYTHONPATH=. python docs/examples/traffic_intersection.py
PYTHONPATH=. python docs/examples/fetch_with_retry.py
```

---

## 1. Traffic intersection — *a complex chart loaded from XState JSON*

**Files:** [`traffic_intersection.json`](./traffic_intersection.json) · [`traffic_intersection.py`](./traffic_intersection.py)

This is the headline example: a non-trivial statechart authored as **plain
XState JSON** (the shape you'd export from the [Stately.ai editor](https://stately.ai/editor))
and loaded with nothing more than `json.load`. The Python file supplies only the
live parts — the named guards, actions, and delay durations — through the
`guards=`, `actions=`, and `delays=` registries.

```python
config = json.load(open("traffic_intersection.json"))
machine = Machine(config, actions=ACTIONS, guards=GUARDS, delays=DELAYS)
```

### What it models

A road intersection with three **parallel** regions that each run on their own
clock, plus a global emergency override:

```
intersection
├── operational  (parallel)
│   ├── northSouth   green ──6s──▶ yellow ──2s──▶ red ──8s──▶ green
│   ├── eastWest     red   ──8s──▶ green  ──6s──▶ yellow ──2s──▶ red
│   └── pedestrian   dontWalk ──PED_REQUEST [crossingIsClear]──▶ walk ──5s──▶ flashing ──3s──▶ dontWalk
│        on EMERGENCY ─────────────────────────────────────────────▶ emergency
└── emergency   entry / allRed
     on CLEAR ──────────────────────────────────────────────────────▶ operational
```

### Features demonstrated

| Feature | Where |
|---|---|
| **Parallel** regions | `operational` runs `northSouth`, `eastWest`, `pedestrian` at once |
| **Nested compound** states | each region is its own `green/yellow/red` chart |
| **Delayed transitions** with **named delays** | `"after": {"nsGreen": "yellow"}` → resolved from `delays={...}` |
| **Guards** | `PED_REQUEST` only crosses when `crossingIsClear` |
| **Entry actions** by name | `pedestrian.walk` entry → `startWalkSignal` |
| **Global event override** | `EMERGENCY` on the parallel parent interrupts every region |
| **`SimulatedClock`** | deterministic time — `clock.increment(ms)` fires due timers |

### Sample output

```
initial                  {'operational': {'eastWest': 'red', 'pedestrian': 'dontWalk', 'northSouth': 'green'}}
after 6s (ns green->)    {'operational': {'eastWest': 'red', 'pedestrian': 'dontWalk', 'northSouth': 'yellow'}}
after +2s (ns yellow->)  {'operational': {'eastWest': 'green', 'pedestrian': 'dontWalk', 'northSouth': 'red'}}
   [action] WALK signal illuminated
PED_REQUEST              {'operational': {'eastWest': 'green', 'pedestrian': 'walk', 'northSouth': 'red'}}
after +5s (walk->flash)  {'operational': {'eastWest': 'green', 'pedestrian': 'flashing', 'northSouth': 'red'}}
   [action] all signals -> RED (emergency)
EMERGENCY                emergency
CLEAR                    {'operational': {'eastWest': 'red', 'pedestrian': 'dontWalk', 'northSouth': 'green'}}
```

---

## 2. Fetch with retry — *the 0.5.0 actor model*

**File:** [`fetch_with_retry.py`](./fetch_with_retry.py)

A data-fetch machine that invokes a flaky service, retries with backoff, and
succeeds on the third attempt. This one is written as a Python `dict` (not a
JSON file) because it uses `invoke`, `context`, and `assign` — which carry live
callables.

```
fetcher
idle ──FETCH──▶ loading
                  invoke: fetchUser (from_promise, input = {user_id})
                    onDone  ─▶ success (assign data)
                    onError ─▶ retrying (assign error, retries += 1)
retrying ──always [exhausted]──▶ failure
         ──after backoff [canRetry]──▶ loading
```

### Features demonstrated

| Feature | Where |
|---|---|
| **`invoke:`** a child actor for a state's lifetime | `loading.invoke` |
| **`from_promise`** actor logic | `actors={"fetchUser": from_promise(fetch_user)}` |
| **`onDone` / `onError`** wiring | resolve → `done.invoke.<id>` / `error.platform.<id>` |
| **`input` from context** | `"input": lambda ctx, ev: {"user_id": ctx["user_id"]}` |
| **`context` + `assign`** | records `data`, `error`, and `retries` |
| **Guards** | `canRetry` gates the backoff retry; `exhausted` ends in `failure` |
| **Delayed retry (`after`)** | `backoff` delay between attempts |

### Sample output

```
initial                value='idle' retries=0
   [fetch] attempt 1 for user 42
FETCH (attempt 1)      value='retrying' retries=1
   [fetch] attempt 2 for user 42
after backoff #1       value='retrying' retries=2
   [fetch] attempt 3 for user 42
after backoff #2       value='success' retries=2

final value : success
loaded data : {'id': 42, 'name': 'Ada Lovelace'}
```

# Statechart workflow direction: evidence and reproductions

**Observation date: November 12, 2026.** This document records the evidence
behind the [statechart workflow roadmap](statechart-workflow-roadmap.md). The
roadmap owns proposed changes, sequencing, acceptance criteria, and release
decisions. This evidence record describes the inspected baseline; it does not
claim that the proposed fixes have landed.

## 1. Frozen baseline and verification scope

| Project | Inspected revision | Purpose in this assessment |
|---|---|---|
| `JovaniPink/xstate-python` | [`d98f2227669770aa78566b32db2d88e318cb2392`](https://github.com/JovaniPink/xstate-python/tree/d98f2227669770aa78566b32db2d88e318cb2392), `master` | Python runtime, parser, actors, persistence, developer tools, and existing tests |
| `simoneCavalleri/fsmc` | [`8d7ce8a71cc881d94ea6888e4ad700634514fd46`](https://github.com/simoneCavalleri/fsmc/tree/8d7ce8a71cc881d94ea6888e4ad700634514fd46), `main` | Compiler organization, normalized definitions, diagnostics, and analysis boundaries |
| `nicolasmelo1/amy` | [`3fee6a5ce1a6dedd1039e0cf4007659e7c0536e2`](https://github.com/nicolasmelo1/amy/tree/3fee6a5ce1a6dedd1039e0cf4007659e7c0536e2), `main` | Application workflow decisions, effects, operational outcomes, and scenario testing |

The Python project declares `0.7.1`, Python 3.13+, and no core runtime
dependencies. It already has hierarchical and parallel statecharts, history,
actors, two interpreters, simulated time, snapshot helpers, Mermaid export,
microstep traces, and a local inspector. Those are existing implementation
assets, not proposed additions. The repository's
[instructions](https://github.com/JovaniPink/xstate-python/blob/d98f2227669770aa78566b32db2d88e318cb2392/AGENTS.md)
protect the `Machine(config, ...)` boundary and SCXML-style execution core.

### Recorded local checks

| Check | Recorded result | Boundary |
|---|---|---|
| Primary suite, excluding `test_scxml.py` | **618 passed**, **92.29%** aggregate coverage with branch measurement enabled | Python **3.13.5**, project installed, development packages matched `poetry.lock` |
| SCXML suite | **57 passed** | **55** configured fixture cases and **2** helper checks; not full W3C conformance |
| `mypy src/xstate/` | Passed, **23 source files** | Locked mypy **1.20.2** |
| `ruff check src/ tests/ scripts/ docs/examples/` | Passed | Locked ruff **0.15.18** |
| Paired runtime probes below | Confirmed the recorded differences | Node **24.22.1**, npm dependency **`xstate@5.33.4`**, Python baseline above |
| Amy `applyPlan` probes | Nine focused assertions passed | Counters, waits, attempts not charged, transition history, and preservation of input values |
| fsmc C++ suite | Not run | Source and tests inspected only |

The first primary-suite attempt had ten subprocess import failures because
the isolated environment did not yet contain an installed checkout. After an
editable installation, all 618 tests passed. Those initial failures are setup
failures, not findings about the library. Coverage measures exercised code;
it does not establish equivalence with another runtime.

The successful baseline commands were:

```bash
python -m pytest tests/ --ignore=tests/test_scxml.py --cov --cov-report=term
python -m pytest tests/test_scxml.py
python -m mypy src/xstate/
python -m ruff check src/ tests/ scripts/ docs/examples/
```

The recorded summaries were:

```text
Required test coverage of 90.0% reached. Total coverage: 92.29%
618 passed in 8.03s
57 passed in 0.08s
Success: no issues found in 23 source files
All checks passed!
```

These receipts apply to the frozen baseline. They are not CI receipts for the
planning PR's eventual head or for later implementation commits. This
assessment did not run the full Python 3.14 matrix, release preflight,
installed-wheel validation, the full Amy suite, or the fsmc suite. Formatting
validation is also separate from the recorded lint command.

The [SCXML harness](https://github.com/JovaniPink/xstate-python/blob/d98f2227669770aa78566b32db2d88e318cb2392/tests/test_scxml.py)
enumerates 55 fixture pairs; its other two tests check inventory/provenance
and path-source import. The fixtures retain
[SCXML Test Framework provenance](https://github.com/JovaniPink/xstate-python/blob/d98f2227669770aa78566b32db2d88e318cb2392/tests/fixtures/scxml/PROVENANCE.md).
Neither a passing subset nor the source project's name establishes full W3C
datamodel or executable-content coverage.

## 2. Observed compatibility differences

The following results came from executing both implementations. The reference
is the pinned **v5.33.4** behavior for these examples, not an assertion that
every v5 feature is in scope. Python registries supply local implementations;
arbitrary JavaScript functions are not portable JSON.

### E1. Numeric delay keys at the actual JSON boundary

Literal JSON containing `"after": {"1000": "b"}` produces a string dictionary
key. Python accepts the configuration, then fails during actor startup with
`UnregisteredImplementationError`. JS starts in `a` and reaches `b` after
1,000 simulated milliseconds. Python examples using integer dictionary keys
do not exercise that serialization boundary.

[`_build_after`](https://github.com/JovaniPink/xstate-python/blob/d98f2227669770aa78566b32db2d88e318cb2392/src/xstate/config_parser.py#L248)
retains the key, while
[`resolve_delay_ms`](https://github.com/JovaniPink/xstate-python/blob/d98f2227669770aa78566b32db2d88e318cb2392/src/xstate/interpreter.py#L61)
treats strings as named implementations. That shared resolver also serves the
async interpreter. Existing `tests/test_after.py` cases establish numeric
Python keys, named delays, callable delays, and missing-name errors.

There is a compatibility decision inside the fix: a numeric-looking registered
name such as `"1000"` currently reaches the Python registry. In the installed
JS reference, `getDelayedTransitions` converts numeric-looking keys before
named-delay resolution. Preserving registry-first behavior and adopting that
JS precedence are different policies. The roadmap requires a collision case
and a documented choice; the probes here establish the ordinary numeric JSON
failure, not every numeric spelling or collision outcome.

### E2. Deferred effects lose their context and triggering event

For `record`, `assign(n=1)`, `record`, `raise(INNER)`, followed by a record on
the `INNER` transition, the reference observes `(0, GO)`, `(1, GO)`,
`(1, INNER)`. Python observes `(1, GO)` three times. An action before assignment
sees later context, and the internally triggered action receives the original
external event.

[`execute_content`](https://github.com/JovaniPink/xstate-python/blob/d98f2227669770aa78566b32db2d88e318cb2392/src/xstate/algorithm.py#L1073)
collects ordinary effects; after the macrostep,
[`Machine._get_actions` and `_bind_action`](https://github.com/JovaniPink/xstate-python/blob/d98f2227669770aa78566b32db2d88e318cb2392/src/xstate/machine.py#L188)
bind them against final context and the outer event. Existing action-order
tests check labels and document ordering, but do not establish per-action
arguments. The trace tests demonstrate internal-event ordering without
establishing the arguments of every deferred callable.

This matters for commands and audit records even when the final state is
correct. The proposed repair belongs in effect capture/binding, while keeping
external work out of pure transition evaluation. Context ownership and copy
cost need explicit treatment; optional trace capture must not become
mandatory merely to preserve action arguments. Stately's
[migration guide](https://stately.ai/docs/migration) and
[action documentation](https://stately.ai/docs/actions) provide terminology;
the executed reference supplies the specific comparison.

### E3. Reentry actions and state-owned resources disagree

For a state targeting itself, Python executes `exit` and `entry` whether
`reenter` is omitted, false, or true. JS does so only for `reenter: true`.
The Python parser reads the older `type: internal/external` convention and
does not interpret `reenter`.

Even with `reenter: true`, Python keeps an invoked callback running and keeps
the existing timer. Resetting a state at 500 ms with `after: 1000` therefore
reaches its destination at the original 1,000 ms; JS resets the deadline to
1,500 ms and stops/restarts the invocation. The callback logs below verify
cleanup and startup, not merely child-object membership.

The relevant owners are
[`_make_transition`](https://github.com/JovaniPink/xstate-python/blob/d98f2227669770aa78566b32db2d88e318cb2392/src/xstate/config_parser.py#L317),
the algorithm's exit/entry computation,
[`Interpreter._sync_delays`](https://github.com/JovaniPink/xstate-python/blob/d98f2227669770aa78566b32db2d88e318cb2392/src/xstate/interpreter.py#L408),
`AsyncInterpreter._sync_delays`, and
[`Actor._reconcile_invocations_once`](https://github.com/JovaniPink/xstate-python/blob/d98f2227669770aa78566b32db2d88e318cb2392/src/xstate/actor.py#L947).
Resource reconciliation uses final active membership, which cannot distinguish
continuous occupancy from exit followed by entry. A parser flag alone cannot
repair that causal information loss.

Existing `test_after.py`, `test_invoke.py`, history/parallel tests, and
`test_startup_queueing.py` are relevant regression locations. Tests must
separate targetless behavior, targeted self-transitions, explicit reentry,
and legacy configuration. The reference
[transition documentation](https://stately.ai/docs/transitions) describes
reentry as restarting invoked actors.

### E4. Top-level completion leaves the Python actor active

A root-invoked callback remains running after Python enters a top-level final
state. Its snapshot reports `done`, its runtime reports `running`, and a root
`REOPEN` transition returns it to `a`. JS runs callback cleanup and ignores
the later event. This is a completion-lifecycle difference, separate from
explicit `stop()` behavior.

Owners are interpreter startup/processing/cleanup in
[`interpreter.py`](https://github.com/JovaniPink/xstate-python/blob/d98f2227669770aa78566b32db2d88e318cb2392/src/xstate/interpreter.py),
the corresponding async boundary, and
[`Actor`](https://github.com/JovaniPink/xstate-python/blob/d98f2227669770aa78566b32db2d88e318cb2392/src/xstate/actor.py).
[`State`](https://github.com/JovaniPink/xstate-python/blob/d98f2227669770aa78566b32db2d88e318cb2392/src/xstate/state.py#L78)
already computes final snapshot status; that status alone does not implement
runtime termination. Existing `test_v5_config.py` tests snapshot status/output,
while `test_actor.py` covers explicit lifecycle calls. Implementation work
must distinguish top-level completion from a nested final state completing
only its containing state.

## 3. Reproduce E1–E4 locally

These are **known-divergence probes**, not a passing compatibility test suite.
Their output intentionally shows failures in the frozen Python baseline. They
perform synthetic local transitions and simulated time only. No application
service or provider credentials are required.

In a new working directory, obtain the exact source and install it into a
Python 3.13 environment. The recorded Python version was 3.13.5:

```bash
git clone https://github.com/JovaniPink/xstate-python.git python-source
git -C python-source checkout --detach d98f2227669770aa78566b32db2d88e318cb2392
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install -e ./python-source
```

Use Node 24.22.1 for the recorded reference. In the same working directory,
save this minimal `package.json`, then install the exact dependency:

```json
{
  "private": true,
  "dependencies": {
    "xstate": "5.33.4"
  }
}
```

```bash
npm install --ignore-scripts --no-audit --no-fund
python compare_python.py
node compare_xstate.cjs
```

Save the two blocks below using those filenames. Keep the generated lockfile
with a local reproduction. The observed package integrity was
`sha512-eGNMu3BNqU0Z85P+ouYG5OCZqIABU+QsW6vUieFt9p9gOGs3C+BL10Exg7XdRPSXPQKlP6XoYpYf93r9VmW8mQ==`.
These instructions do not add npm or a JS runtime dependency to the Python
library; they describe a separate reference environment.

### Python probe

```python
from xstate import Machine, SimulatedClock, assign, create_actor, from_callback, interpret, raise_

log = []
machine = Machine(
    {"id": "m", "context": {"n": 0}, "initial": "a", "states": {
        "a": {"on": {"GO": {"target": "b", "actions": ["record", assign({"n": 1}), "record", raise_("INNER")]}}},
        "b": {"on": {"INNER": {"target": "c", "actions": "record"}}},
        "c": {},
    }},
    actions={"record": lambda ctx, event: log.append((ctx["n"], event.name))},
)
service = interpret(machine).start()
service.send("GO")
print("action binding", log)
service.stop()

for reenter in [None, False, True]:
    log = []
    transition = {"target": "a"}
    if reenter is not None:
        transition["reenter"] = reenter
    machine = Machine(
        {"id": "m", "initial": "a", "states": {"a": {"entry": "enter", "exit": "exit", "on": {"GO": transition}}}},
        actions={"enter": lambda: log.append("enter"), "exit": lambda: log.append("exit")},
    )
    service = interpret(machine).start()
    log.clear()
    service.send("GO")
    print("self transition reenter", reenter, log)
    service.stop()

log = []
def source():
    log.append("start child")
    return lambda: log.append("stop child")

machine = Machine(
    {"id": "m", "initial": "a", "states": {"a": {"invoke": {"id": "worker", "src": "worker"}, "on": {"RESET": {"target": "a", "reenter": True}}}}},
    actors={"worker": from_callback(source)},
)
actor = create_actor(machine).start()
print("child after start", log)
actor.send("RESET")
print("child after reenter true", log)
actor.stop()

# Real JSON object keys are strings, including numeric-looking delay keys.
import json
machine = Machine(json.loads('{"id":"timer","initial":"a","states":{"a":{"after":{"1000":"b"}},"b":{}}}'))
try:
    actor = create_actor(machine, clock=SimulatedClock()).start()
    print("JSON timer initially", actor.get_snapshot().value)
    actor.stop()
except Exception as error:
    print("JSON timer", type(error).__name__, str(error))
print("child after stop", log)

clock = SimulatedClock()
machine = Machine({"id": "m", "initial": "a", "states": {"a": {"after": {1000: "b"}, "on": {"RESET": {"target": "a", "reenter": True}}}, "b": {}}})
actor = create_actor(machine, clock=clock).start()
clock.increment(500)
actor.send("RESET")
clock.increment(500)
print("timer after 500ms post reset", actor.get_snapshot().value)
clock.increment(500)
print("timer after 1000ms post reset", actor.get_snapshot().value)
actor.stop()

log = []
def worker():
    log.append("started")
    return lambda: log.append("stopped")

machine = Machine(
    {"id": "m", "initial": "a", "invoke": {"id": "worker", "src": "worker"}, "on": {"REOPEN": ".a"}, "states": {"a": {"on": {"DONE": "done"}}, "done": {"type": "final"}}},
    actors={"worker": from_callback(worker)},
)
actor = create_actor(machine).start()
actor.send("DONE")
print("terminal snapshot", actor.get_snapshot().status, actor.get_snapshot().value, "runtime", actor.status, "log", log)
actor.send("REOPEN")
print("after REOPEN", actor.get_snapshot().status, actor.get_snapshot().value)
actor.stop()
```

### JavaScript reference probe

```javascript
// Read-only reference probes against package-lock-pinned XState 5.33.4.
// Run: node compare_xstate.cjs
const { createMachine, createActor, assign, raise, fromCallback, SimulatedClock } = require('./node_modules/xstate');
console.log('XState', require('./node_modules/xstate/package.json').version);
let log = [];
let m = createMachine({id:'m',context:{n:0},initial:'a',states:{a:{on:{GO:{target:'b',actions:['record',assign({n:1}),'record',raise({type:'INNER'})]}}},b:{on:{INNER:{target:'c',actions:'record'}}},c:{}}},{actions:{record:({context,event})=>log.push([context.n,event.type])}});
let a = createActor(m).start();
a.send({type:'GO'});
console.log('action binding', JSON.stringify(log));
a.stop();

const jsonMachine = createMachine(JSON.parse('{"id":"timer","initial":"a","states":{"a":{"after":{"1000":"b"}},"b":{}}}'));
const jsonClock = new SimulatedClock();
const jsonActor = createActor(jsonMachine, {clock:jsonClock}).start();
console.log('JSON timer initially', jsonActor.getSnapshot().value);
jsonClock.increment(1000);
console.log('JSON timer at 1000', jsonActor.getSnapshot().value);
jsonActor.stop();
for (const reenter of [undefined,false,true]) {
  log = [];
  const transition = {target:'a'};
  if (reenter !== undefined) transition.reenter = reenter;
  m = createMachine({id:'m',initial:'a',states:{a:{entry:'enter',exit:'exit',on:{GO:transition}}}},{actions:{enter:()=>log.push('enter'),exit:()=>log.push('exit')}});
  a = createActor(m).start();
  log = [];
  a.send({type:'GO'});
  console.log('self transition reenter', String(reenter), JSON.stringify(log));
  a.stop();
}
log = [];
m = createMachine({id:'m',initial:'a',states:{a:{invoke:{id:'worker',src:'worker'},on:{RESET:{target:'a',reenter:true}}}}},{actors:{worker:fromCallback(()=>{log.push('start child');return ()=>log.push('stop child')})}});
a = createActor(m).start();
console.log('child after start', JSON.stringify(log));
a.send({type:'RESET'});
console.log('child after reenter true', JSON.stringify(log));
a.stop();
console.log('child after stop', JSON.stringify(log));
const clock = new SimulatedClock();
m = createMachine({id:'m',initial:'a',states:{a:{after:{1000:'b'},on:{RESET:{target:'a',reenter:true}}},b:{}}});
a = createActor(m,{clock}).start();
clock.increment(500);
a.send({type:'RESET'});
clock.increment(500);
console.log('timer after 500ms post reset', a.getSnapshot().value);
clock.increment(500);
console.log('timer after 1000ms post reset', a.getSnapshot().value);
a.stop();
log = [];
m = createMachine({id:'m',initial:'a',invoke:{id:'worker',src:'worker'},on:{REOPEN:'.a'},states:{a:{on:{DONE:'done'}},done:{type:'final'}}},{actors:{worker:fromCallback(()=>{log.push('started');return ()=>log.push('stopped')})}});
a = createActor(m).start();
a.send({type:'DONE'});
console.log('terminal snapshot', a.getSnapshot().status, a.getSnapshot().value, 'log', log);
a.send({type:'REOPEN'});
console.log('after REOPEN', a.getSnapshot().status, a.getSnapshot().value);
a.stop();
```

### Recorded Python output

```text
action binding [(1, 'GO'), (1, 'GO'), (1, 'GO')]
self transition reenter None ['exit', 'enter']
self transition reenter False ['exit', 'enter']
self transition reenter True ['exit', 'enter']
child after start ['start child']
child after reenter true ['start child']
JSON timer UnregisteredImplementationError Delay '1000' is not configured. Pass it via Machine(config, delays={'1000': ...}).
child after stop ['start child', 'stop child']
timer after 500ms post reset b
timer after 1000ms post reset b
terminal snapshot done done runtime running log ['started']
after REOPEN active a
```

### Recorded JavaScript output

```text
XState 5.33.4
action binding [[0,"GO"],[1,"GO"],[1,"INNER"]]
JSON timer initially a
JSON timer at 1000 b
self transition reenter undefined []
self transition reenter false []
self transition reenter true ["exit","enter"]
child after start ["start child"]
child after reenter true ["start child","stop child","start child"]
child after stop ["start child","stop child","start child","stop child"]
timer after 500ms post reset a
timer after 1000ms post reset b
terminal snapshot done done log [ 'started', 'stopped' ]
after REOPEN done done
```

Both assembled scripts were rerun successfully and reproduced these outputs.
They print observations rather than asserting equivalence. The future runner
in [issue #55](https://github.com/JovaniPink/xstate-python/issues/55) should
give passing fixtures and acknowledged divergences distinct, reviewable
outcomes; deleting a failing fixture would not establish compatibility.

## 4. Existing issues and parser validation observations

### Observable input: issue #53

The advertised unary observable factory fails when its positional parameter
is named `count` rather than `input`:

```python
import asyncio
from xstate import create_actor, from_observable

async def numbers(count):
    for value in range(count):
        yield value

async def main():
    actor = create_actor(from_observable(numbers), input=3).start()
    await asyncio.sleep(0)
    snapshot = actor.get_snapshot()
    print(snapshot.status, type(snapshot.error).__name__, str(snapshot.error))
    actor.stop()

asyncio.run(main())
```

Recorded result: `error TypeError numbers() missing 1 required positional
argument: 'count'`. This is already tracked by
[#53](https://github.com/JovaniPink/xstate-python/issues/53).
[`_ObservableBackend.start`](https://github.com/JovaniPink/xstate-python/blob/d98f2227669770aa78566b32db2d88e318cb2392/src/xstate/actor.py#L554)
uses keyword-name filtering. Existing `tests/test_async_actors.py` and the
safe signature-binding cases in `tests/test_promise_callable_contract.py`
provide relevant coverage patterns. Factory errors must retain their original
meaning; retrying execution after catching `TypeError` would risk calling a
factory twice.

### Snapshot restoration and live context: issue #54

A completed snapshot with callable final output produced `{'answer': 42}`.
Serialization retained that value; deserialization returned `None`. The
minimal sequence is:

```python
import json
from xstate import Machine, deserialize_snapshot, serialize_snapshot

machine = Machine({
    "id": "finish", "initial": "working", "context": {"answer": 42},
    "states": {
        "working": {"on": {"FINISH": "done"}},
        "done": {
            "type": "final",
            "output": lambda context, event: {"answer": context["answer"]},
        },
    },
})
snapshot = machine.transition(machine.initial_state, "FINISH")
payload = json.loads(json.dumps(serialize_snapshot(snapshot)))
restored = deserialize_snapshot(machine, payload)
print(snapshot.output, payload["output"], restored.output)
```

Recorded result: `{'answer': 42} {'answer': 42} None`.
[`deserialize_snapshot`](https://github.com/JovaniPink/xstate-python/blob/d98f2227669770aa78566b32db2d88e318cb2392/src/xstate/snapshot.py#L77)
constructs `State` without the saved output. The
[persistence guide](https://github.com/JovaniPink/xstate-python/blob/d98f2227669770aa78566b32db2d88e318cb2392/docs/concepts/persistence.md)
explicitly describes reconstruction, so preserving output is a proposed
contract improvement tracked in
[#54](https://github.com/JovaniPink/xstate-python/issues/54), not an
undocumented promise already fulfilled. `tests/test_snapshot.py` and
`tests/test_v5_config.py` are the primary test owners.

A separate probe changed `actor.get_snapshot().context["answer"]` to `99`;
a subsequent `get_snapshot()` exposed `{'answer': 99}` without a transition.
Snapshot isolation between computations and immutable configuration/action
containers do not make live dictionary context deeply immutable. A detached
observation API or read-only projection requires an explicit compatibility
decision.

### Strict parser gaps

`Machine(config, strict=True)` accepted duplicate explicit state IDs and an
atomic state containing children. These are observed acceptance results, not
a claim that every malformed model executes. In
[`Machine._register`](https://github.com/JovaniPink/xstate-python/blob/d98f2227669770aa78566b32db2d88e318cb2392/src/xstate/machine.py#L308),
the later duplicate replaces the ID-map entry. The
[`StateNodeConfigParser`](https://github.com/JovaniPink/xstate-python/blob/d98f2227669770aa78566b32db2d88e318cb2392/src/xstate/config_parser.py)
validates selected shapes and handler/guard references; strict mode is not a
complete model verifier. `test_architecture_refactor.py`, `test_setup.py`,
and `test_target_paths.py` are useful locations for structured validation
coverage. Static analysis should report opaque guards as unknown and avoid
executing application handlers merely to inspect a model.

## 5. Intentional runtime and persistence boundaries

The baseline [runtime guide](https://github.com/JovaniPink/xstate-python/blob/d98f2227669770aa78566b32db2d88e318cb2392/docs/concepts/runtimes.md)
already documents the following behavior. These are roadmap constraints,
not additional newly discovered defects:

- `AsyncInterpreter` awaits machine actions but does not start invoked actors
  or route actor-tree messages. Tests in `test_async_actor_boundary.py` make
  its warnings and exclusions explicit.
- Machine-backed `Actor` uses the synchronous interpreter. It supports
  invocation, including async child logic, but does not await machine actions.
  An event loop must exist on the thread starting an async child; the default
  timer worker does not marshal that work to another thread's loop.
- Both interpreters commit the computed snapshot before effects execute.
  Action failure leaves that snapshot committed and skips remaining actions
  and notification; it supplies no transactional rollback.
- Inspection runs after snapshot installation and before effect completion.
  A trace frame records chart progress, not confirmation that an external
  command succeeded.

Persistence excludes queued events, pending timer deadlines, child internals,
subscriptions, and effect progress. Restoring an active actor restarts its
timers with full configured delays and reconciles children from configuration.
The documented host responsibilities include version compatibility, context
validation, and avoiding duplicate live actors. These helpers do not establish
durable or exactly-once execution. The roadmap separates narrow restoration
changes from a future host's event, revision, and effect-recovery contract.

## 6. Evidence from fsmc and amy

### fsmc: useful compiler organization; bounded analysis claims

The inspected
[`FsmIr`](https://github.com/simoneCavalleri/fsmc/blob/8d7ce8a71cc881d94ea6888e4ad700634514fd46/include/fsm/ir/fsm_ir.hpp)
and
[`TransitionEdge`](https://github.com/simoneCavalleri/fsmc/blob/8d7ce8a71cc881d94ea6888e4ad700634514fd46/include/fsm/ir/transition_edge.hpp)
separate model representation from frontends and consumers. Its
[`Diagnostic`](https://github.com/simoneCavalleri/fsmc/blob/8d7ce8a71cc881d94ea6888e4ad700634514fd46/include/fsm/diagnostic/diagnostic_engine.hpp)
contains severity, code, message, source span, help, and secondary locations;
the engine exposes text, JSON, and GitHub annotation output. These are concrete
patterns for one reusable interpretation of a chart and actionable validation.

The Python parser already resolves a state tree in two passes. Its nodes
contain raw configuration, mutable runtime structures, and Python bindings;
they are not an already published portable IR. Any normalization work must
preserve region and transition order and separate declaration identity from
callable implementation identity.

Source inspection of fsmc's
[`model_checker.cpp`](https://github.com/simoneCavalleri/fsmc/blob/8d7ce8a71cc881d94ea6888e4ad700634514fd46/src/middleend/analysis/model_checker.cpp)
found guards retained as edge metadata and `verify_property` returning success
when the property AST is absent. That observation does not prove that every
CLI path accepts an invalid property: upstream parsing may reject it first.
It does establish that this assessment cannot treat the README's broad formal
verification language as a verified semantic contract. No C++ build,
performance benchmark, external prover run, or full format round-trip was
performed. Borrowing diagnostics does not import a proof of arbitrary Python
guards, real-time execution, or external effects.

### amy: explicit workflow outcomes and scenario tools

Amy's
[`Plan` and `applyPlan`](https://github.com/nicolasmelo1/amy/blob/3fee6a5ce1a6dedd1039e0cf4007659e7c0536e2/packages/core/src/work.ts)
distinguish act, advance, wait, and settled. Work records separate observations
from charged attempts and retain transition reasons. The nine focused
assertions exercised this function; they were not an end-to-end worker or
crash-recovery test. Its
[`workflow assembly`](https://github.com/nicolasmelo1/amy/blob/3fee6a5ce1a6dedd1039e0cf4007659e7c0536e2/packages/core/src/define-workflow.ts),
[`scenario walker`](https://github.com/nicolasmelo1/amy/blob/3fee6a5ce1a6dedd1039e0cf4007659e7c0536e2/packages/workflow-testkit/src/walk.ts),
and
[`conformance checks`](https://github.com/nicolasmelo1/amy/blob/3fee6a5ce1a6dedd1039e0cf4007659e7c0536e2/packages/workflow-testkit/src/conformance.ts)
show how observation, decision, effects, result folding, and test coverage can
form a coherent application workflow.

Its
[`Mermaid parser`](https://github.com/nicolasmelo1/amy/blob/3fee6a5ce1a6dedd1039e0cf4007659e7c0536e2/packages/core/src/diagram.ts)
explicitly rejects composite states and concurrent regions. Forks represent
child workflow calls while the parent record remains in one flat state;
edge labels are prose, not executable guard/event bindings. These boundaries
make it inspiration for a workflow layer, not an interchangeable replacement
for the Python statechart engine.

The inspected
[`worker`](https://github.com/nicolasmelo1/amy/blob/3fee6a5ce1a6dedd1039e0cf4007659e7c0536e2/plugins/serial-engine/src/Worker.ts)
performs effects, persistence, successor enqueueing, and queue completion in
separate operations; it logs an undrawn transition after saving the changed
record. The
[`file store`](https://github.com/nicolasmelo1/amy/blob/3fee6a5ce1a6dedd1039e0cf4007659e7c0536e2/plugins/file-store/src/FileStore.ts)
uses temporary writes and rename. Neither observation establishes a transaction
over all resources or exactly-once external effects. The full Amy suite and
production deployment behavior were not verified.

Both reference repositories retain MIT notices in their pinned
[fsmc license](https://github.com/simoneCavalleri/fsmc/blob/8d7ce8a71cc881d94ea6888e4ad700634514fd46/LICENSE)
and [Amy license](https://github.com/nicolasmelo1/amy/blob/3fee6a5ce1a6dedd1039e0cf4007659e7c0536e2/LICENSE).
This planning document proposes architectural adaptations; it does not copy
their implementations into the runtime or change the Python project's
[upstream attribution](https://github.com/JovaniPink/xstate-python/blob/d98f2227669770aa78566b32db2d88e318cb2392/LICENSE).

## 7. What this evidence supports

The baseline suite is healthy for its current tests, while the paired probes
expose material gaps in the intended interchange contract. The evidence
supports a pinned supported subset, causal effect/lifecycle records,
structured diagnostics, and scenario tests built on existing clocks/traces.
It does not support full v5 equivalence, arbitrary Mermaid execution, general
formal verification, or durable workflow claims. Planned acceptance criteria
and the migration choices needed to close those gaps remain in the
[roadmap](statechart-workflow-roadmap.md).

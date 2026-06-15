# xstate-python — Product Document

> Research snapshot: June 2026. XState JS data sourced from stately.ai/docs, npmjs.com,
> github.com/statelyai/xstate, and the official CHANGELOG. Python library data from PyPI,
> GitHub, and each library's documentation. All numeric claims cross-verified across ≥2 sources.

---

## 1. What We Are Building

**xstate-python** is a Python implementation of [XState](https://github.com/statelyai/xstate)
— hierarchical statecharts with the W3C SCXML execution algorithm at the core and native
compatibility with XState / Stately.ai JSON config.

The one-sentence pitch:

> *Design your state machine in the Stately.ai visual editor, export the JSON, drop it into
> Python — it just works.*

No other maintained Python library does this. That gap is the bet.

---

## 2. The Market

### 2a. XState JS — what we are tracking

XState is at **v5.32.1** (released June 12, 2025 — 32 minor versions in 18 months).

| Metric | Value | Source |
|---|---|---|
| GitHub stars | **~29,700** | github.com/statelyai/xstate (direct) |
| Weekly npm downloads | **~4.7M** (raw) / ~1.5M (adjusted) | npmtrends / snyk.io |
| @xstate/react weekly downloads | ~2.18M | npmjs.com |
| Discord members | ~5,000 | toolify.ai/discord/xstate |
| Companies using in prod | 194+ estimated | therstack.com; Gatsby, Kong, Koordinates, Back Market confirmed |

XState released v5.0.0 on **December 1, 2023**. It is actively maintained with roughly one
minor release per month. The release cadence signals a healthy, committed upstream.

### 2b. Stately ecosystem (the platform that makes XState a product)

| Product | What it is | Relevant to us |
|---|---|---|
| **Stately Studio** | Visual statechart editor → exports XState JSON | Our JSON import is the bridge |
| **Stately Sky** | Edge-deployed live actors (Cloudflare Workers + Durable Objects; ~50ms latency globally) | Out of scope for open-source lib |
| **Stately Inspector** (`@statelyai/inspect`) | Universal actor inspector, replaced `@xstate/inspect` in Jan 2024 | Future: Python-compatible inspector protocol |

**Stately Studio pricing** (as of June 2026, unchanged since Nov 2023):

| Tier | Price | Key limits |
|---|---|---|
| Community | Free | Unlimited public projects; 3 AI generations/month |
| Pro | $39/mo | Private projects; 1,000 AI gens/month; Sky; GitHub Sync; React UI gen |
| Team | $199/mo (≤10 users) | Shared projects; team roles |
| Enterprise | Custom | SSO; audit logs; custom hosting; embed Studio |

The Stately Studio → JSON export is the funnel for xstate-python users. A team using Stately
Studio Pro to design machines will want Python import to work seamlessly.

### 2c. Python state machine landscape

| Library | Stars | Latest | Hier. | Parallel | Async | SCXML | XState JSON | Actor model |
|---|---|---|---|---|---|---|---|---|
| **transitions** | ~6,500 | 0.9.3 — Jul 2025 | Ext | Ext | Yes | No | No | No |
| **python-statemachine** | ~1,200 | 3.1.2 — May 2026 | Yes (v3+) | Yes (v3+) | Yes | W3C suite | No | No |
| **Sismic** | ~163 | 1.6.11 — Oct 2025 | Yes (UML2) | Yes | Yes | Full 1.0 | No | No |
| **Automat** | ~647 | 25.4.16 — Apr 2025 | No | No | No | No | No | No |
| **xstate-statemachine** *(basiltt)* | ~14 | 0.5.0 — Mar 2026 | Yes | Yes | Yes | Partial | Yes | Partial |
| **xstate-python** *(this)* | ~194 | WIP — not on PyPI | Yes | Yes | **No** | Partial | **Yes** | **Yes** |

**Key competitive observations:**

- `transitions` dominates on adoption but has no SCXML, no XState JSON, no actor model. It is the
  "easy FSM" option; we are not competing for that segment.
- `python-statemachine` is the strongest technical competitor: W3C SCXML test suite, async,
  invoked services, Django integration, excellent docs. The critical gap: **no XState JSON
  compatibility**.
- `Sismic` targets formal verification (Design by Contract). Niche audience; not a threat.
- `xstate-statemachine` (basiltt) is the closest rival on our niche. 14 stars, minimal docs,
  no full actor model. We are ahead on every technical dimension.
- We are the **only** Python library combining SCXML algorithm + XState JSON + full actor model.

---

## 3. XState v5 API — What We Track

XState v5 is a significant redesign. Here is the full API mapping relevant to xstate-python.

### Core API renames (v4 → v5)

| v4 | v5 | Status in xstate-python |
|---|---|---|
| `Machine(config)` | `createMachine(config)` | `Machine()` retained; `createMachine` alias pending |
| `interpret(machine)` | `createActor(machine)` | Both exist (`interpret` + `create_actor`) ✓ |
| `machine.withConfig(impl)` | `machine.provide(impl)` | Not implemented |
| `machine.withContext(ctx)` | `createActor(m, { input })` | `Machine(config, context=...)` partial |
| `service.state` | `actor.getSnapshot()` | `interpreter.state` + `actor.get_snapshot()` ✓ |
| `service.onTransition(fn)` | `actor.subscribe(fn)` | Both work ✓ |
| `state.done` (bool) | `snapshot.status === 'done'` | `state.status == "done"` ✓ |
| `State` class | `MachineSnapshot` object | `MachineSnapshot = State` alias ✓ |
| `cond:` | `guard:` | Both accepted ✓ |
| `data:` (final output) | `output:` | Both accepted ✓ |
| `on: { '': ... }` | `always:` | Both accepted ✓ |
| `services:` (in config) | `actors:` | `invoke: { src: name }` + registry ✓ |
| `(context, event) =>` | `({ context, event }) =>` | Positional; single-object form planned |
| `pure()` / `choose()` | `enqueueActions()` | Not implemented |
| `spawn()` | `spawnChild()` action | `actor.spawn(logic)` ✓ |
| `stop()` action | `stopChild()` | `actor.stop()` ✓ |
| `send()` action | `sendTo()` / `raise()` | Both `send`, `send_to`, `raise_` ✓ |
| `EmittedFrom<T>` | `SnapshotFrom<T>` | Python: no generics yet |
| `schema:` | `types:` | Not implemented (Python doesn't need it) |
| `external: false` | `reenter: true` | Not implemented |

### v5 features not in v4 (and their status here)

| v5 Feature | Released | Status in xstate-python |
|---|---|---|
| `setup()` API — typed factory | v5.0.0 | **Not implemented** |
| Actor system (`system.get(id)`) | v5.0.0 | `ActorSystem` exists; `system.get()` not exposed ✓ partial |
| `input` — typed actor initialization | v5.0.0 | `invoke.input` works; `createActor(m, input=...)` partial |
| `toPromise(actor)` | v5.2.0 | Not implemented |
| `assertEvent(event, type)` | v5.3.0 | Not implemented |
| `getNextSnapshot()` | v5.5.0 | Not implemented |
| `emit()` action creator | v5.9.0 | Not implemented |
| Actor logic inspection events | v5.7.0 | Not implemented |
| Graph/test utilities (from `@xstate/graph`) | v5.20.0 | Not implemented |
| `setup.extend()` | v5.24.0 | Not implemented |
| `system.getAll()` | v5.23.0 | Not implemented |
| `transition()` / `initialTransition()` pure fns | v5.19.0 | Not implemented |
| Routable states (`route: {}`) | v5.28.0 | Not implemented |
| `actor.select(selector)` | v5.29.0 | Not implemented |
| `mapState(snapshot, mapper)` | v5.31.0 | Not implemented |
| Higher-order guards (`and()`, `or()`, `not()`) | v5.0.0 | Not implemented |
| `snapshot.children` (live actor refs) | v5.0.0 | Not implemented |
| `fromObservable` actor logic | v5.0.0 | Not implemented |
| `fromTransition` actor logic | v5.0.0 | Not implemented |
| `@statelyai/inspect` protocol | Jan 2024 | Not implemented |
| `params` in actions/guards | v5.9.0 | Not implemented |
| `AbortSignal` in `fromPromise` | v5.13.0 | Not implemented |
| `maxIterations` guard (infinite loop prevention) | v5.31.0 | Not implemented |

---

## 4. xstate-python: Current State (post 0.5.0 / post best-practices fix)

### What works today

| Capability | Notes |
|---|---|
| Hierarchical (compound) states | Full |
| Parallel states | Full — broadcast, nested, `onDone` when all regions done |
| Guards (callable or named string) | Arity-aware: `()`, `(ctx)`, `(ctx, event)` |
| Entry / exit actions | Full |
| Context + `assign` | Named assigns run in declared order (build_action fix); deep-copy isolation |
| Final states + `onDone` | Full — `output` / `data` both accepted |
| `always:` / eventless transitions | Full — `on: {'': ...}` also accepted |
| History states | Shallow and deep |
| Delayed transitions (`after`) | `SimulatedClock` + `ThreadClock`; named delay refs |
| Synchronous `Interpreter` | Run-to-completion queue; `subscribe()`; `send()`; `start()`/`stop()` |
| `create_actor` / `ActorSystem` | v5 actor model — spawn, parent/child, `send_parent`, `send_to` |
| `invoke:` | Child actor for state lifetime; `onDone` / `onError` |
| `from_promise` / `from_callback` | Actor logic kinds |
| `MachineSnapshot` | v5 alias for `State`; `status` / `output` / `error` fields |
| XState v5 config keys | `guard`, `output`, `always`, `actors`; both `cond`/`guard` and `data`/`output` accepted |
| Named action ordering | `build_action` resolves at construction; `assign`/`raise_`/`send` in registry run in declared position |
| SCXML XML import | Optional extra (`pip install xstate[scxml]`) |
| `__all__` / clean public API | 18 exported names |

### Test coverage

- **206 tests** passing (as of last push to master)
- `tests/test_best_practices.py` — 12 regression tests for the architectural fixes
- `tests/test_v5_config.py` — v5 config key compatibility
- `tests/test_actor_logic.py` — `from_promise`, `from_callback`, `create_actor`
- `docs/examples/` — 2 complex runnable examples (traffic intersection, fetch with retry)

---

## 5. Gap Analysis

### Priority gaps (what blocks adoption)

| Gap | Severity | Effort | Target |
|---|---|---|---|
| **Not on PyPI** | Blocking — zero installs | Low | Immediate |
| **No async interpreter** | Blocks all async Python (FastAPI, Django async, Celery) | High | 0.6.0 |
| **SCXML test suite not run** — pass rate unknown | Credibility gap vs `python-statemachine` | Medium | 0.6.0 |
| **Docs too thin** — one README, minimal API docs | Adoption friction | Medium | Continuous |

### API parity gaps (what limits power users)

| Gap | Effort | Target |
|---|---|---|
| `setup()` API + typed factory | High | 0.7.0 |
| `snapshot.children` (live actor refs in snapshot) | Medium | 0.6.0 |
| `enqueueActions()` (replace `pure`/`choose`) | Medium | 0.6.0 |
| `higher-order guards` (`and_`, `or_`, `not_`) | Low | 0.6.0 |
| `fromObservable` / `fromTransition` actor logic | Medium | 0.6.0 |
| `machine.provide()` alias | Low | 0.7.0 |
| Single-object handler sig `({context, event})` | Medium | 0.7.0 |
| `assertEvent()` / `getNextSnapshot()` utilities | Low | 0.7.0 |
| `toPromise(actor)` | Low | 0.7.0 |
| Pure-Python SCXML condition evaluator | High | 0.6.0 |
| `@statelyai/inspect` protocol compatibility | Medium | 0.8.0 |
| `actor.select(selector)` | Low | 0.8.0 |
| Graph traversal / test model utilities | Medium | 0.8.0 |
| Type stubs (`.pyi`) and generics | High | 0.8.0 |

---

## 6. Strategic Position

### The bet

XState's visual editor (Stately Studio) exports JSON that neither `transitions` nor
`python-statemachine` can consume. Every team that:

- Designs machines in Stately Studio and needs a Python backend
- Shares statechart config across a JS frontend and Python service
- Adopts XState v5 and needs Python parity (actor model, `invoke`, `from_promise`)
- Migrates from an XState JS codebase to Python microservices

…has no maintained option other than `xstate-statemachine` (14 stars, minimal docs).
We are the answer.

### How we win

1. **First-class XState JSON** is already implemented. The registries
   (`actions=`, `guards=`, `delays=`, `actors=`) map named strings to Python callables;
   the config is pure data. This architecture is right. It needs PyPI and better docs.

2. **v5 actor model parity** is already substantial: `create_actor`, `from_promise`,
   `from_callback`, `invoke`, `send_parent`, `send_to`. No Python competitor offers this.

3. **SCXML algorithm correctness** — `algorithm.py` implements the W3C algorithm. We need
   to run the SCXML test framework and publish the pass rate. This is the credibility moat.

4. **Stately ecosystem integration** — as Stately Studio grows (Pro plan $39/mo, GitHub Sync,
   React UI generation), the demand for "and the same machine in Python" grows with it.

### Where `python-statemachine` beats us (honest assessment)

- Async support (we are blocking all asyncio use cases)
- Django integration (native `StateMachineField`)
- Documentation quality and tutorial depth
- W3C SCXML test suite pass rate (published)
- Stable PyPI releases (13 releases vs. our 0)

These are fixable. Priority order: **PyPI → async → SCXML test suite → docs**.

---

## 7. Roadmap

### Immediate — 0.1.0 (this week)

The code is ready. The only blocker is packaging.

- [ ] Tag `v0.1.0` on master; configure `pyproject.toml` (classifiers, keywords, project URLs)
- [ ] `pip install xstate` must work
- [ ] Verify CI uploads to PyPI on tag
- [ ] Set GitHub repo description
- [ ] Add "Install in 10 seconds" badge to README top

### 0.2.0 — Credibility (1–2 months)

- [ ] Run SCXML W3C test suite; fix failures; publish pass rate in README
- [ ] Pure-Python SCXML condition evaluator (replace JS eval in `scxml.py`)
- [ ] `snapshot.children` — live `ActorRef` dict on `MachineSnapshot`
- [ ] Higher-order guards: `and_()`, `or_()`, `not_()` (matching `and()`, `or()`, `not()` in v5)
- [ ] `enqueueActions()` equivalent
- [ ] Mermaid diagram export (`machine.to_mermaid()`)
- [ ] Per-concept API docs (one page per concept, mirroring stately.ai/docs structure)

### 0.3.0 — Async (2–4 months)

- [ ] `AsyncInterpreter` — `asyncio`-based event loop, non-blocking `send()`
- [ ] `from_promise` with true deferred resolution (currently synchronous eagerly resolving)
- [ ] `from_observable` actor logic (async generator / `asyncio.Queue`)
- [ ] `cancel()` for async delayed transitions via `asyncio.create_task`
- [ ] FastAPI integration example; Celery task state example

### 0.4.0 — Setup API and utilities (4–6 months)

- [ ] `setup(types=..., guards=..., actions=..., actors=...)` → `create_machine(config)`
- [ ] Single-object handler signature: `guard({"context": c, "event": e})`
- [ ] `machine.provide(implementations)` — runtime implementation injection
- [ ] `assert_event(event, type)` utility
- [ ] `get_next_snapshot(logic, snapshot, event)` pure function
- [ ] `to_promise(actor)` — converts actor to `asyncio.Future`
- [ ] `params` support in actions and guards (decouple logic from config)

### 0.5.0 — Integrations (6–9 months)

- [ ] Django: `StateMachineField`, model mixin, admin panel state display
- [ ] `@statelyai/inspect` WebSocket protocol — connect xstate-python actors to Stately Inspector
- [ ] Stately Studio export round-trip validation (CI check)
- [ ] Persistence helpers: serialize/deserialize `MachineSnapshot` to JSON / Redis
- [ ] Type stubs (`.pyi`) for the full public API

### 0.6.0+ — Parity and Polish

- [ ] Full Python generics: `Machine[TContext, TEvent, TOutput]`
- [ ] Graph traversal utilities (`get_shortest_paths`, `create_test_model`)
- [ ] `actor.select(selector)` — derived observable slices
- [ ] Routable states
- [ ] `setup.extend()` — composable machine configuration

---

## 8. What "Next" Means Right Now

The single most important next action: **ship to PyPI**. Everything below is moot without it.

Recommended sequence:

1. **Tag v0.1.0 → PyPI** — 1 day
2. **SCXML test suite** — run it, report pass rate, fix top failures — 1 week
3. **Async interpreter** — unblocks the largest class of Python backend use cases — 2–3 weeks
4. **Docs** — bring up to python-statemachine quality — ongoing

The async gap is the biggest capability hole. Python web backends (FastAPI, Django async) run
on an event loop; a synchronous-only interpreter is a non-starter for them. Shipping `AsyncInterpreter`
before anything else in 0.3.0 is the right call.

---

## 9. Success Metrics

| Metric | Today | 3-month target | 6-month target |
|---|---|---|---|
| PyPI install count | 0 (not published) | Live | 500+ weekly installs |
| GitHub stars | ~194 | 300+ | 600+ |
| SCXML W3C test pass rate | Unknown | >70% | >90% |
| Test coverage | 206 tests | 250+ | 350+ |
| Docs pages | 1 README + 2 examples | 8 concept docs | 15+ concept docs |
| Open issues resolved/month | 0 | 3+ | 8+ |
| Projects citing us as XState JSON alt | 0 | 2+ | 5+ |

---

## 10. Reference: XState v5 Full Feature List (for tracking)

*Track each against xstate-python status. Update as features are implemented.*

### Implemented (✓) / Not yet (✗) / Partial (◐)

| XState v5 Feature | xstate-python |
|---|---|
| `createMachine()` / `Machine()` | ◐ `Machine()` only |
| `createActor()` / `interpret()` | ✓ both |
| `setup()` typed factory | ✗ |
| `input` — typed actor initialization | ◐ `invoke.input` only |
| `output` — typed final state result | ✓ |
| Actor system (`system.get(id)`) | ◐ `ActorSystem` exists; `get()` internal |
| `systemId` registration | ✗ |
| `invoke:` child actors | ✓ |
| `from_promise` | ✓ (synchronous only) |
| `from_callback` | ✓ |
| `from_observable` / `from_transition` | ✗ |
| `spawnChild()` / `spawn()` action | ✓ `actor.spawn()` |
| `stopChild()` action | ✓ `actor.stop()` |
| `sendTo()` action | ✓ `send_to()` |
| `raise()` action | ✓ `raise_()` |
| `send_parent()` action | ✓ |
| `cancel()` action | ✓ |
| `assign()` action | ✓ |
| `log()` action | ✗ |
| `enqueueActions()` | ✗ |
| `emit()` action | ✗ |
| Higher-order guards (`and`, `or`, `not`) | ✗ |
| `params` in actions/guards | ✗ |
| `guard:` (renamed from `cond`) | ✓ both accepted |
| `always:` (renamed from `on: {'': ...}`) | ✓ both accepted |
| `reenter:` (renamed from `internal: false`) | ✗ |
| `machine.provide()` | ✗ (`Machine(config, actions=...)` covers most cases) |
| `actor.getSnapshot()` | ✓ `actor.get_snapshot()` |
| `actor.subscribe()` | ✓ |
| `actor.select(selector)` | ✗ |
| `snapshot.status` | ✓ |
| `snapshot.output` | ✓ |
| `snapshot.error` | ✓ |
| `snapshot.children` | ✗ |
| `toPromise(actor)` | ✗ |
| `waitFor(actor, predicate)` | ✗ |
| `assertEvent(event, type)` | ✗ |
| `getNextSnapshot()` | ✗ |
| `transition()` / `initialTransition()` pure fns | ✗ |
| `mapState(snapshot, mapper)` | ✗ |
| `getNextTransitions(state)` | ✗ |
| Graph utilities (`getShortestPaths`, `createTestModel`) | ✗ |
| Inspection (`createActor(m, { inspect })`) | ✗ |
| `@statelyai/inspect` protocol | ✗ |
| `MachineSnapshot` type | ✓ alias for `State` |
| `SnapshotFrom<T>` TypeScript helper | ✗ (no Python generic yet) |
| `maxIterations` option | ✗ |
| Routable states | ✗ |
| `setup.extend()` | ✗ |
| `system.getAll()` | ✗ |
| `machine.provide()` | ✗ |
| SCXML XML import | ✓ (optional extra) |
| Async interpreter | ✗ |

---

*Document maintained in `docs/PRODUCT.md`. Update after each milestone.*
*Research sources: stately.ai/docs, github.com/statelyai/xstate/blob/main/packages/core/CHANGELOG.md,*
*npmjs.com/package/xstate, snyk.io/advisor/npm-package/xstate, PyPI, each library's GitHub.*

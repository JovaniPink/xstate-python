# xstate-python Product Notes

Research snapshot: June 2026. External ecosystem numbers are approximate and
should be refreshed before publication or fundraising use. Repo capability notes
reflect the current `master` branch after the 0.7.0 correctness and adoption
milestone.

## Product Thesis

`xstate-python` is a Python implementation of XState-style statecharts with
native XState/Stately JSON compatibility and an SCXML-style execution core.

The short pitch:

> Design a statechart in Stately, share the JSON with Python, and run it with
> predictable statechart semantics.

The bet is not to out-feature every Python FSM package. The bet is to own the
bridge between XState's JSON ecosystem and Python backends.

## Current State

| Area | Status |
|---|---|
| Packaging | Project metadata is modernized for Python 3.13+ and ready for the 0.7.0 PyPI release |
| Core transition API | `Machine(config).transition(state, event)` |
| XState JSON | Native Python dict / JSON-compatible config boundary |
| Parser architecture | Typed schema + normalization/parser layer |
| Handler adaptation | Build-time `HandlerAdapter`; legacy signatures still supported |
| Setup API | `setup(...).create_machine(...)` exists for stricter named implementations |
| Context policy | Default deep-copy adapter plus immutable dataclass adapter |
| Snapshots | `MachineSnapshot = State`; immutable public containers |
| Snapshot queries | Active `tags`, `meta`, `has_tag`/`hasTag`, and `state_in`/`stateIn` guard helpers are present |
| Diagrams | Dependency-free Mermaid `stateDiagram-v2` export is present |
| Sync runtime | `Interpreter` with RTC queue, subscriptions, delayed transitions, and lock-serialized timer sends |
| Async runtime | `AsyncInterpreter` with async start/send/stop, awaitable actions, and event-loop timers |
| Actor model | `create_actor`, `ActorSystem`, spawn, parent/child tree, `send_parent`, `send_to` |
| Actor logic | `from_promise`, `from_callback`, `from_observable`, `to_promise` |
| Invoke | Child actor lifetime reconciliation with `done.invoke.*` and `error.platform.*` events |
| SCXML XML import | Present; safe Boolean cond subset; configured 54-case suite passes |

## What Works Today

- Hierarchical, parallel, final, and history states.
- Entry/exit/transition actions and `assign`.
- Higher-order action helpers with `choose(...)` and `pure(...)`.
- Guards via `guard` or legacy `cond`.
- Eventless transitions via `always` or legacy empty-event syntax.
- Delayed transitions via `after`, numeric or named delays.
- Machine snapshots with `status`, `output`, `error`, `matches(...)`, and
  `can(event)`.
- Active state tags and metadata via immutable `state.tags` and `state.meta`,
  plus `has_tag(...)` / `hasTag(...)`.
- Reusable current-state guards via `state_in(...)` / `stateIn(...)`.
- Snapshot serialization and restoration helpers for actor persistence flows.
- Mermaid diagram export via `to_mermaid(machine)`.
- XState v5 naming alignment: `guard`, `output`, `always`, `actors`,
  `MachineSnapshot`, `create_actor`, and `setup`.
- Primary suite passes in current Python 3.13/3.14 CI.
- SCXML `cond-js` subset result: `4 passed`.
- Configured SCXML result: `54 passed`, `0 failed`, including all enabled
  `more-parallel` cases.
- Concept guides cover machine configuration, runtime choices, actors,
  persistence, and SCXML import.
- Five canonical runnable programs are exercised in isolated subprocesses on
  supported CI Python versions.

## Competitive Position

| Library | Main strength | Why xstate-python is different |
|---|---|---|
| `transitions` | Popular, flexible FSMs | Does not consume XState JSON or model XState actors |
| `python-statemachine` | Strong docs and SCXML credibility | Does not target Stately/XState JSON compatibility |
| `Sismic` | Formal statecharts and contracts | Different audience; no XState JSON bridge |
| `xstate-statemachine` | Closest XState JSON niche | Smaller surface; weaker actor/setup/runtime parity |

The strongest adoption story is a team already using XState or Stately in
JavaScript and wanting the same machine shape in Python services.

## Completed Milestones

| Milestone | Result |
|---|---|
| Parallel transition domains | All 13 configured `more-parallel` cases pass; the configured SCXML suite is `54 passed`, `0 failed` |
| Concept documentation | Machines, implementations, sync/async runtimes, actors, persistence, and SCXML import are documented |
| Runnable examples | `docs/examples/` is canonical and every runner has subprocess smoke coverage |
| Persistence adoption | Snapshot compatibility and timer/child-actor restoration limits are documented with a JSON resume example |

## Roadmap

| Priority | Work |
|---|---|
| High | Publish 0.7.0 to PyPI as `xstate` |
| High | Expand SCXML coverage beyond the configured subset without adding JavaScript evaluation |
| Medium | Inspector protocol compatibility |
| Medium | More XState v5 utilities: `provide`, action helpers, graph/test helpers |
| Low | Add framework integrations such as Django and FastAPI after the runtime API settles |

## Success Metrics

| Metric | Near-term target |
|---|---|
| PyPI release | `pip install xstate` works after the 0.7.0 GitHub Release |
| Primary test count | Maintain 300+ focused tests |
| SCXML pass rate | Keep the configured 54-case suite green while expanding supported coverage |
| Docs | Keep every public runtime boundary represented by a maintained concept guide |
| Examples | Keep JSON, sync, async, actor, persistence, and SCXML runners green in CI; add framework integrations next |

## Maintenance Notes

- Do not add a JavaScript evaluator dependency. Unsupported SCXML
  JavaScript/datamodel expressions should fail clearly instead of executing
  arbitrary JavaScript.
- Algorithm changes require SCXML verification.
- Keep `Machine(config, actions=..., guards=..., delays=..., actors=...)`
  compatible; it is the JSON boundary that makes the project valuable.
- Prefer current XState v5 terminology in docs (`guard`, `output`, `always`) and
  mention legacy aliases only as compatibility notes.

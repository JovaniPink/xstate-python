# xstate-python Product Notes

Product direction updated November 20, 2026. Capability notes describe the
unreleased 0.7.1 source candidate. Proposed application and integration work is
identified separately from existing library behavior.

The maintainer's direction is **Pythonic first**: a useful Python statechart
library with an LLM-assisted software-development niche to investigate.
The [agent-workflow research](plans/pythonic-agent-workflows-research.md) records
current Codex, Claude Code, Antigravity, Python-library, and Measured Skills
evidence, architecture options, and staged acceptance criteria. It updates the
product priority of the [November 12 plan](plans/statechart-workflow-roadmap.md)
while preserving its correctness contracts.

## Product Thesis

`xstate-python` is a Python statechart and actor library with an SCXML-style
execution core and an explicitly tested data-only XState subset. Its developer
experience should center Python domain models, functions, typing, and explicit
runtime behavior. JSON interoperability remains a supported capability.

The short pitch:

> Model software workflows in Python, make their decisions inspectable, and
> keep the evidence for advancing work attached to the revision it describes.

The first application hypothesis is coordinating agent-assisted contributions
and reviews across changing goals, code revisions, checks, and sessions.
Revision-aware review records, provider adapters, and a durable application
host are proposed work. They are not shipped features of the current library.

The [compatibility contract](concepts/xstate-compatibility.md) pins the reference
runtime and records exact observations. Its synthetic fixtures do not yet prove
that representative Stately exports run unchanged. That remains an adoption
gate, alongside the documented argument-timing, startup-order, and persistence
limits. Re-entry and completion now have fixture-level lifecycle evidence.

The product hypothesis is that explicit state and current acceptance evidence
can reduce handoff mistakes and reconstruction effort in Python development
workflows. That benefit must be measured against ordinary prompts, repository
documents, and existing CI before expanding runtime obligations.

## Current State

| Area | Status |
|---|---|
| Packaging | Python 3.13+ source and wheel metadata are prepared for 0.7.1; package-index name and ownership remain unresolved |
| Core transition API | `Machine(config).transition(state, event)` |
| XState JSON | Dict/JSON boundary with a pinned, fixture-level compatibility contract and explicit known differences |
| Parser architecture | Typed schema + normalization/parser layer |
| Handler adaptation | Setup-time `HandlerAdapter` for declared handlers; dynamic `pure` results normalize during computation; legacy signatures still supported |
| Action arguments | Deferred effects capture context at their action position and retain the effective event/parameter references; the causal fixture is required parity |
| Setup API | `setup(...).create_machine(...)` exists for stricter named implementations |
| Context policy | Default deep-copy adapter for snapshots and each deferred action; immutable dataclass adapter avoids copying |
| Snapshots | `MachineSnapshot = State`; immutable public containers |
| Snapshot queries | Active `tags`, `meta`, `has_tag`/`hasTag`, and `state_in`/`stateIn` guard helpers are present |
| Diagrams | Dependency-free Mermaid `stateDiagram-v2` export is present |
| Sync runtime | `Interpreter` with RTC queue, subscriptions, delayed transitions, and lock-serialized timer sends |
| Async runtime | `AsyncInterpreter` with async start/send/stop, awaitable actions, and event-loop timers |
| Actor model | `create_actor`, `ActorSystem`, spawn, parent/child tree, `send_parent`, `send_to` |
| Actor logic | `from_promise`, `from_callback`, `from_observable`, `to_promise` |
| Re-entry | Boolean `reenter`, defaulting to false for JSON; retained resources survive and exited/re-entered owners reset; explicit legacy/SCXML policy remains available |
| Invoke | Child reconciliation before public notifications, replacement on owner re-entry, and guarded emissions from replaced invocations |
| Completion | Terminal machine runtimes retain final snapshots, release owned work, and ignore later events; pure done transitions emit no actions |
| SCXML XML import | Present; safe Boolean and narrow integer-data subset; configured 57-case suite passes |

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
- Configured SCXML result: `57 passed`, `0 failed`, including all enabled
  `more-parallel` cases.
- Concept guides cover machine configuration, runtime choices, actors,
  persistence, and SCXML import.
- Five canonical runnable programs are exercised in isolated subprocesses on
  supported CI Python versions.

## Competitive Position

| Reference | Lesson to apply | Evidence and implication |
|---|---|---|
| Python state-machine libraries | Domain models, typed interfaces, useful rejection reasons, explicit runtime contracts | Primary-source comparison in the [research](plans/pythonic-agent-workflows-research.md#2-what-to-learn-from-state-machine-libraries) |
| yay-machine | Concise state-oriented APIs and maintained examples | Adapt the ergonomics to Python while preserving this library's semantics |
| Coding-agent harnesses | Existing execution, continuation, skills, sessions and artifacts | Integrate supported surfaces; additional prompt execution alone is weak differentiation |
| Measured Skills | Acceptance vocabulary, bounded review, and a prepared comparison study | Test a specific coordination need before implementing a host |

The candidate niche is revision-aware acceptance and review coordination around
Python software delivery. The research also identifies an existing
`python-statemachine` coding-assistant example, so "state machines for agents"
alone is not an established differentiator. Shared-definition interoperability
remains a separate useful adoption experiment.

## Decisions Challenged By Current Evidence

Python usability and demonstrated application value now lead product discovery.
The statechart core, application examples, provider adapters, and durable host
have separate responsibilities and acceptance gates. Existing compatibility
cases remain required even when a Python-focused feature does not depend on a
shared JavaScript chart.

| Assumption | Evidence needed before expanding the claim |
|---|---|
| Loading XState-shaped JSON establishes equivalent behavior | Exact cross-runtime observations, including action arguments, lifecycle, and timing; matching snapshots alone are insufficient |
| Pythonic means renaming JavaScript APIs | A typed Python consumer example with ordinary domain objects, clear errors, explicit resource ownership, and measured friction |
| Agent continuation is a missing feature | Current providers already offer continuation; demonstrate a separate evidence/revision problem |
| More tests make the library more useful | Advertised behavior remains verified and a representative consumer outcome improves against a documented baseline |
| A workflow host is the natural next feature | Observed coordination/recovery need, measured benefit, and explicit ownership of transactions, effects, and operations |
| An independent name creates differentiation | A demonstrated Python use case, maintained guarantees, and confirmed distribution ownership |

These are delivery gates, not demonstrated customer demand. The prepared
Measured review comparison is a useful evidence gate for the proposed niche.
A representative shared chart is still needed to substantiate the broader
interoperability story; equivalent named implementations remain necessary.

## Completed Milestones

| Milestone | Result |
|---|---|
| Shared-runtime contracts | 18 scenarios / 66 commands against pinned XState; 14 required parity cases cover the checked delay, action, re-entry, and completion behavior, with four exact known differences |
| Parallel transition domains | All 15 configured `more-parallel` cases pass; the configured SCXML suite is `57 passed`, `0 failed` |
| Concept documentation | Machines, implementations, sync/async runtimes, actors, persistence, and SCXML import are documented |
| Runnable examples | `docs/examples/` is canonical and every runner has subprocess smoke coverage |
| Persistence adoption | Snapshot compatibility and timer/child-actor restoration limits are documented with a JSON resume example |

## Roadmap

The [agent-workflow research](plans/pythonic-agent-workflows-research.md#11-staged-delivery-plan)
owns the proposed product sequence. The [earlier plan](plans/statechart-workflow-roadmap.md)
retains detailed core acceptance and migration work. Rows other than **Done**
are proposed outcomes, not completed features.

| Sequence | Work |
|---|---|
| Done | Pinned XState v5 comparison contract with literal JSON delays, causal action arguments, re-entry, child/timer lifecycle, and final completion ([#55](https://github.com/JovaniPink/xstate-python/issues/55); PRs #60–#62) |
| Immediate runtime work | Define output restoration and preserve completed output ([#54](https://github.com/JovaniPink/xstate-python/issues/54)); repair observable factory input independently ([#53](https://github.com/JovaniPink/xstate-python/issues/53)) |
| Product validation | Observe contribution/review work and use the prepared Measured comparison to distinguish prompt, skill, and coordination value |
| First application, if justified | A typed revision-aware review example over recorded events, with current evidence, stable finding IDs, and explicit stopping conditions ([#56](https://github.com/JovaniPink/xstate-python/issues/56)) |
| Ongoing | Preserve all 14 required parity cases; keep four known differences explicit and promote cases only after reviewed fixes |
| Compatibility experiment | Validate one representative shared chart; measure unchanged structure, observable behavior, and transition/context-capture cost |
| Consumer-driven core work | Improve structured validation, restoration identity, and scenario/trace tools where the examples expose a concrete gap |
| After demonstrated need | One optional provider adapter; a durable host only after recovery requirements justify its transaction and effect responsibilities |
| Parallel decision | Resolve distribution ownership, naming, namespace, and migration before publication ([#57](https://github.com/JovaniPink/xstate-python/issues/57)) |
| Separate follow-up | Expand the supported SCXML subset without JavaScript evaluation, evaluate XState v6, and assess inspector protocol, `provide`, or graph utilities against concrete consumers |
| Later extraction | Reusable Python authoring or typed state views and a second provider after repeated consumer needs establish the interface |

## Success Metrics

| Metric | Near-term target |
|---|---|
| Package distribution | An approved package name installs the reviewed 0.7.1 artifact after ownership and publication are verified |
| Compatibility evidence | Every advertised fixture passes against the pinned reference; any unexpected mismatch or stale known difference fails CI |
| Python usability | One maintained typed application example with documented setup, clear rejection behavior, and recorded consumer friction |
| Coordination value | Compare stale-evidence incidents, lost findings, verification effort, and setup cost against documents/prompts/CI; no improvement claimed before observations |
| Shared-definition adoption | One representative consumer chart loads unchanged in both runtimes with explicit equivalent bindings and matching observations |
| Performance evidence | Reproducible measurements for representative charts, context sizes, action counts, context policy, and tracing mode; separate runtime cost from model latency and human effort |
| SCXML pass rate | Keep the configured 57-case suite green while expanding supported coverage |
| Docs | Keep every public runtime boundary represented by a maintained concept guide |
| Examples | Keep JSON, sync, async, actor, persistence, and SCXML runners green in CI; add adapters only for a demonstrated consumer need |

## Maintenance Notes

- Do not add a JavaScript evaluator dependency. Unsupported SCXML
  JavaScript/datamodel expressions should fail clearly instead of executing
  arbitrary JavaScript.
- Algorithm changes require SCXML verification.
- Keep `Machine(config, actions=..., guards=..., delays=..., actors=...)`
  compatible while improving the Python experience around the same core.
- Prefer current XState v5 terminology in docs (`guard`, `output`, `always`) and
  mention legacy aliases only as compatibility notes.

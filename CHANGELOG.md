# Changelog

All notable changes to this project will be documented here.

## 0.7.1 - Unreleased

### Added

- Added a development-only comparison contract using shared JSON, pinned
  XState 5.33.4 and Node 24.22.1, independent expected observations, and exact
  known-divergence cases. A separate CI job runs the comparison. The corpus
  now covers 18 scenarios / 66 commands, with 14 required parity cases and four
  exact known differences, including completed child-reference representation.

- Added an optional standard-library local inspector for the JSON fetch/retry
  example, with event and simulated-time controls, active-state visualization,
  bounded microstep history, synthetic scenarios, JSON export, and equivalence
  tests against direct actor execution.

- Added a typed docking controller facade over a JSON chart, deterministic
  success/timeout/cancellation demos, bounded structural Markdown trace replay,
  failure and context-policy guidance, and a dependency-free local benchmark
  separating transitions, serialized controller ticks, trace capture, and
  report formatting. Controller calls and timer delivery serialize, cancelled
  callbacks are discarded before admission, and unfinished drive cleanup is
  retried independently of chart phase.
- Added optional snapshot annotations to `to_mermaid(machine, snapshot=...)`,
  marking active state captions while preserving configured initial arrows.
- Added generic typing across machine configuration, handlers, events,
  snapshots, sync and async interpreters, actor logic, setup, and persistence
  APIs while retaining unparameterized `Machine(config, ...)`, raw JSON data,
  string events, and legacy handler compatibility.
- Added XState v5 event descriptor selection for exact event names, partial
  wildcards ending in `.*`, and the `*` catch-all, with exact and
  longest-prefix candidates taking precedence while preserving guarded
  fallthrough.
- Added XState v5 transition target paths for sibling descendants and
  dot-prefixed children, including multi-target arrays, while retaining
  `#id` targets.
- Added optional macrostep bounds through `max_iterations` and portable
  `options.maxIterations` configuration. Exceeding the bound raises
  `InfiniteLoopError` before another microstep runs, and interpreters retain
  their last committed snapshot.
- Added immutable `TransitionTrace`, `MicrostepTrace`, and `MacrostepTrace`
  records, `get_initial_microsteps(...)` and `get_microsteps(...)` helpers, and
  local inspection callbacks for sync and async interpreters and
  machine-backed actors. This inspection surface does not implement the
  `@statelyai/inspect` wire protocol.
- Added the runtime-checkable structural `ActorRef` boundary, plus
  `CompletionSnapshot` and `SubscriptionProtocol` typing contracts;
  `to_promise(...)` now accepts compatible structural actor references.
- Vendored the SCXML Test Framework fixtures exercised by the configured suite
  under `tests/fixtures/scxml/`, including upstream provenance, license
  custody, and an exact-inventory test.
- Added the fixture-proven SCXML integer-data subset: non-negative integer
  initialization, same-variable `+ 1` assignment, and strict integer equality
  guards.

### Changed

- JSON transitions now default to `reenter: false`; explicit `reenter` accepts
  only Booleans. **Migration:** charts relying on implicit external self or
  descendant transitions need `reenter: true` for a modern reset, or an explicit
  legacy `type: external` to retain the earlier transition-domain policy.
  Explicit legacy `type` remains supported when `reenter` is absent; SCXML
  import preserves its external default. Modern and SCXML parallel domains are
  not claimed to be equivalent. See the
  [re-entry guide](docs/concepts/machines-and-implementations.md#re-entry-and-migration).
- Renamed the comparison field `children.active` to `children.ids`, preserving
  each runtime's reference keys without filtering stopped JavaScript references.
- The default context adapter now deep-copies context for each deferred action.
  **Migration:** use `assign` for chart updates; mutating an action's context
  changes neither committed state nor other effects' contexts. Custom adapters
  retain control of context ownership. Event payloads and action parameters
  retain reference semantics, callable action parameters are not evaluated,
  and action `HandlerArgs.state` remains `None`. See the
  [handler contract and copying costs](docs/concepts/machines-and-implementations.md#action-arguments-and-migration).
- Clarified the async interpreter and machine actor capability boundary.
  `AsyncInterpreter` warns about declared invocations and executed actor
  messages; the synchronous interpreter warns when an action returns an
  awaitable without closing or canceling it. See the runtime guide for details.
- Removed the SCXML fixture submodule so local, CI, and release validation use
  the same repository-owned test inputs without a separate checkout step.
- Expanded the enabled `more-parallel` conformance subset from 13 to 15 cases;
  the configured suite now reports 57 passing cases.
- Changed public actor-system lookup, parent, and child references to widened
  `ActorRef` values while keeping `create_actor(...)` and `spawn(...)` return
  types precise when actor logic is known.
- Avoided trace-only context snapshots unless a trace helper or interpreter
  inspector requests them, and cached transition exit sets during parallel
  conflict resolution.
- Changed `ThreadClock` from one thread per timer to one on-demand scheduler
  thread per clock.

### Fixed

- Reconciled timers and invocations from actual macrostep exits. Retained owners
  keep their resources; exited and re-entered owners cancel/reset timers and
  replace children. Transient states do not start new timers or invocations.
  The child-reentry fixture now requires parity with its unchanged XState oracle.
- Moved machine-actor invocation reconciliation after actions and before public
  snapshot notifications, so lifecycle work no longer depends on subscriber
  ordering. Late callback emissions after stop and completion emissions from
  replaced invocation instances are ignored; valid messages already queued,
  including during cleanup, retain their queue semantics.
- Completed machines now include final active-state exit effects in reverse
  document order and preserve their final snapshot/output while ignoring
  remaining raised/eventless work and later external events. Pure transitions
  from a done snapshot return no actions, and `can(event)` returns false.
- Machine runtimes now enter terminal `done` status, release owned timers and
  children, unregister completed actors, and prevent restart. Terminal-effect
  failure still triggers cleanup without rolling back the committed snapshot.
  Async completion settles queued callers and awaits cancelled timer tasks
  without cancelling or awaiting the task currently completing the machine.
- Actor completion and explicit stop now attempt all child teardown and clear
  ownership before surfacing cleanup errors. A failing callback cleanup is not
  repeated by a later stop attempt.
- Deferred action handlers now receive context captured at their action
  position and the effective event, including internal/eventless steps.
  Named/inline, entry/exit, and `choose`/`pure` effects use the same captures in
  macrostep results and microstep traces. The causal comparison fixture now
  requires parity with its unchanged XState expectations.
- Named delays on synchronous `send`, `send_parent`, and `send_to`, and async
  self-sends, now receive the send action's captured context/event. Evaluation
  still occurs after snapshot commit; `after` expressions continue to use the
  committed context and outer event.
- Actions returned by `pure` now reuse parser normalization, including nested
  named actions, guards, `choose`/`pure`, and custom context adapters.

- Numeric JSON `after` keys now schedule millisecond delays in both runtimes.
  Finite nonnegative decimal/exponent spellings are supported; overflowing
  numeric keys fail during construction. A numeric key takes precedence over
  a same-named delay registry entry. Rename numeric registry keys used by
  `after` to descriptive names when migrating; string delays in `send` keep
  their registry behavior. See the [compatibility guide](docs/concepts/xstate-compatibility.md).

- Promise actors now pass their input to ordinary positional parameters even
  when the parameter is not named `input`, matching the public callable type.
  Optional and variadic positional parameters now receive actor input, even
  alongside `**kwargs`. Wrap a function in a zero-argument callable to retain
  its own default; `**kwargs`-only handlers continue receiving `input`.
  Uninspectable callables now receive input positionally; wrap them when they
  require a zero-argument or keyword-only call.

- Queued events sent during interpreter startup until initial actions and the
  initial notification finish, in both runtimes and machine-backed actors.
  Startup failures and async cancellation now release queue ownership and
  settle waiting callers; stopping skips remaining actions and notifications.
- Corrected macrostep ordering so state exits, transition actions, and state
  entries execute in SCXML order while one FIFO internal queue carries raised
  events across eventless and internal-event microsteps.
- Corrected legacy atomic self-transition handling inside parallel states so the
  source branch exits and re-enters without cycling active sibling regions.
- Prevented actor stop and invocation reconciliation from leaving a running
  child, and prevented late spawns from remaining registered after parent stop.
- Made sync and async interpreter stop terminal, made async stop wait for owned
  timer task cancellation to settle, and skipped later runtime actions after a
  concurrent stop.
- Made serialized snapshot value, context, and output data independent from the
  live snapshot, added explicit custom context codecs, and kept the immutable
  configuration authoritative if a caller mutates the derived state value.
- Completed strict generic annotations across all 23 source files.

## 0.7.0 - 2026-07-02

### Added

- Added active snapshot tags and metadata: `state.tags`, read-only
  `state.meta`, `state.has_tag(...)`, and the XState-compatible
  `state.hasTag(...)` alias.
- Added reusable current-state guard helpers via `state_in(...)` and
  `stateIn(...)`.
- Added higher-order action helpers: `choose(...)` for guarded action branch
  selection and `pure(...)` for dynamically computed action lists.
- Added dependency-free Mermaid `stateDiagram-v2` export with
  `to_mermaid(machine)`.
- Added concept guides for machine configuration, runtime choices, actors,
  snapshot persistence, and SCXML import.
- Added tested async workflow, snapshot resume, and SCXML import examples, with
  subprocess smoke coverage for every canonical program in `docs/examples/`.

### Changed

- Hardened the GitHub Release publish workflow so the release tag must match the
  package version, point at `origin/master`, and have a configured PyPI token
  before upload.
- Unified local and GitHub release validation through
  `scripts/release_preflight.py`, with a manual `v0.7.0` dry-run workflow
  against `master` and contract tests that prevent workflow gate drift.
- Updated PyPI-facing installation docs to use `pip install xstate` for the
  released package.
- Consolidated runnable examples under `docs/examples/` and removed the legacy
  untested top-level scripts.
- Hardened SCXML import with canonical `guard` handlers, document-global ID and
  required-attribute validation, XML whitespace-aware targets, and full MyPy
  coverage.
- Added a release artifact gate that installs the built wheel in an isolated
  environment and checks package metadata, typing markers, imports, and a live
  actor transition before publication.
- Promoted unhandled test warnings to failures, raised the minimum coverage
  threshold from 50% to 90%, and modernized canonical guards and examples to
  the `HandlerArgs` and `guard` conventions.

### Fixed

- Corrected SCXML transition-domain resolution so external transitions inside
  parallel states re-enter every affected region and resolve conflicts in
  document order.
- Made state entry actions run in document order and exit actions run in
  reverse document order, including nested and parallel configurations.

## 0.6.0 - 2026-06-28

### Added

- Added the `setup(...).create_machine(...)` builder for XState v5-style named
  actions, guards, delays, and actors.
- Added composable guard helpers: `and_`, `or_`, and `not_`.
- Added snapshot serialization and restoration helpers:
  `serialize_snapshot(...)` and `deserialize_snapshot(...)`.
- Added observable actor helpers with `from_observable(...)` and
  `to_promise(...)`.
- Added public project context docs and refreshed user-facing documentation for
  the current architecture and runtime behavior.

### Changed

- Made Python 3.13+ the supported release floor.
- Modernized the release workflow for Poetry 2.x and current GitHub Actions.
- Kept the core runtime dependency-free, including SCXML import and the safe
  SCXML Boolean `cond` evaluator.
- Improved sync interpreter runtime safety around delayed sends and timer-driven
  callbacks.

### Fixed

- Replaced stale release metadata and outdated Python/Poetry workflow settings.
- Aligned docs, packaging metadata, and CI expectations for the 0.6.0 release.

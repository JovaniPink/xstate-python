# Changelog

All notable changes to this project will be documented here.

## 0.7.1 - Unreleased

### Added

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

- Removed the SCXML fixture submodule so local, CI, and release validation use
  the same repository-owned test inputs without a separate checkout step.
- Expanded the enabled `more-parallel` conformance subset from 13 to 15 cases;
  the configured suite now reports 57 passing cases.
- Changed public actor-system lookup, parent, and child references to widened
  `ActorRef` values while keeping `create_actor(...)` and `spawn(...)` return
  types precise when actor logic is known.

### Fixed

- Corrected macrostep ordering so state exits, transition actions, and state
  entries execute in SCXML order while one FIFO internal queue carries raised
  events across eventless and internal-event microsteps.
- Corrected atomic self-transition handling inside parallel states so the
  source branch exits and re-enters without cycling active sibling regions.

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

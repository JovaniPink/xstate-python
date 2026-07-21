# Changelog

All notable changes to this project will be documented here.

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
- Updated PyPI-facing installation docs to use `pip install xstate` for the
  released package.
- Consolidated runnable examples under `docs/examples/` and removed the legacy
  untested top-level scripts.

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

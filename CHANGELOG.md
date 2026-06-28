# Changelog

All notable changes to this project will be documented here.

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

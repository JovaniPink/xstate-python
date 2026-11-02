# Local fetch inspector design and validation

## Objective
Make the existing fetch-with-retry example explorable through a local browser.
Completion requires observable event and clock controls, ordered microstep
history, and reproducible comparisons with direct actor execution. Keep XState
JSON as the chart boundary and core runtime dependencies empty.

## Current evidence
The implementation builds on `master` at `00f203d`. The existing actor runtime
owns invocation and completion, `SimulatedClock` owns time, and immutable
`MacrostepTrace` / `MicrostepTrace` values supply inspection observations.
No execution algorithm is implemented in the browser.

Startup ordering is covered by `tests/test_startup_queueing.py`. The repair in
[PR #46](https://github.com/JovaniPink/xstate-python/pull/46), merged as
`d553f3b`, is an ancestor of that baseline. Its final head `51e9de9` passed both
hosted Python test lanes, SCXML smoke, and code quality. The inspector relies on
this existing behavior; it does not repair startup queueing.

## Interfaces
- `docs/examples/fetch_with_retry.json` owns the chart, including literal
  synthetic invoke input for user 42.
- `build_machine(scenario)` in `fetch_with_retry.py` returns a fresh machine and
  synthetic source. Named Python actions, guards, delays, and actor logic supply
  implementations. Scenarios are immediate success, two failures then success,
  and exhausted retries.
- `InspectorSession` in `local_inspector.py` owns one actor, clock, command log,
  and bounded trace projection. Events pass through `actor.send`; time passes
  through `clock.increment`. It never assigns a destination state directly.
- `make_server(port=0)` binds only `127.0.0.1`. GET `/` reads the current run;
  POST `/` sends an event, advances time, or resets into a fresh scenario.
  Successful POST redirects to GET to avoid resubmission on ordinary refresh.
- GET `/export` returns an example-specific version-1 JSON document containing
  config, scenario, commands, simulated time, attempt count, current snapshot,
  retained frames, and an omitted-frame count. This is not a public core API.

The default flow is `idle → loading → retrying → loading → retrying → loading →
success`. Exhausted retries take an eventless transition from retrying to
failure. One command can cause multiple macrosteps; each macrostep can contain
multiple microsteps. Records preserve their ordering and selected transitions.

## Implementation steps
1. Extract the JSON chart and fresh scenario factory while retaining the direct
   CLI example's default outcome.
2. Project existing traces into JSON at capture time; do not retain mutable
   snapshot context references or execute actions from the UI.
3. Add a standard-library server and server-rendered forms, active-state diagram,
   snapshot panel, expandable microsteps, source display, reset, and export.
4. Add equivalence and transport tests, documentation, and example type checking
   in the existing CI workflow.

## Test strategy
Each scenario constructs an inspector, a directly operated actor with inspection,
and a directly operated actor without inspection. Compare every command's
snapshot and attempt count, then compare the exact ordered microstep/transition
sequence using an independent projection. Assert explicit expected terminal states,
retry counts, and data, so agreement on an incorrect result cannot pass.

Include partial time advances, ignored payload events, eventless failure,
truncation, reset, stop with pending timers, independent fresh resources, malformed
requests, lifecycle-event rejection, HTML escaping, invalid Unicode, and request
Host/Origin/token checks. The newest 200 frames are retained with sequence numbers;
the command limit rejects command 201 before execution.

Run the repository's primary suite, configured SCXML suite, Ruff, core and example
mypy, lock validation, build, and isolated installed-wheel smoke. The browser
rehearsal covers recovery, reset, and exhausted retries. It is not a complete
accessibility or responsive-layout audit.

## Rollout and rollback
Ship as a source-checkout example. There is no core import side effect, install
extra, remote service, external asset dependency, or package release. Ctrl-C stops
the actor and closes the listener. Reset discards the in-memory run; export first
to retain it. Reverting the example, tests, documentation, and CI type-check step
removes the feature without a data migration.

## Checkpoints
Compare direct execution before browser acceptance. Review the final public diff,
then validate the exact proposed PR head on hosted CI. Record head-specific CI
links in the PR rather than treating local checks as a hosted result. Review and
release acceptance remain separate from draft publication.

## Risks
Inspection observes committed chart state before side effects and actor
reconciliation complete. Frames are observations, not external-completion
receipts. The current snapshot is read after a command returns.

This is a single-session local development tool. Requests serialize on the
server thread, and tabs share the session. It uses literal loopback Host checks,
Origin checks, per-process form tokens, bounded request sizes, timeouts, and
escaped output. Synthetic context and user-supplied event payloads appear in the
export; it is not a redacted operational-data exporter.

Layout supports this example's five flat states. Editable charts, arbitrary
Python bindings, remote inspection, and general statechart layout are outside
scope. A second simulator in JavaScript was rejected because it would duplicate
runtime semantics. No implementation code was copied from the motivating
[state-machine playground](https://github.com/eli-felse/state-machine-playground).

## Stopping conditions
Stop for unexpected concurrent edits, mismatched runtime results, conflicting
upstream changes, or failing required gates. Diagnose any necessary core-runtime
repair separately instead of hiding it in the inspector change.

## Validation receipt
The PR records the exact commit, local Python 3.13/3.14 gate results, hosted CI,
and review limits. See [the guide](../concepts/local-inspector.md) for reproducible
commands and expected outcomes.

### Local results (2026-11-02)

All commands ran from the repository root in separate environments installed from
`poetry.lock`. The PR records the final commit SHA and hosted results.

| Component | Command | Python 3.13.1 | Python 3.14.4 |
|---|---|---|---|
| Primary tests | `poetry run python -m pytest tests/ --ignore=tests/test_scxml.py --cov --cov-report=term` | 592 passed; 92.23% core coverage | 592 passed; 91.64% core coverage |
| Configured SCXML | `poetry run python -m pytest tests/test_scxml.py` | 57 passed | 57 passed |
| Core types | `poetry run mypy src/xstate/` | Passed (23 files) | Passed (23 files) |
| Example types | `poetry run mypy --explicit-package-bases docs/examples/fetch_with_retry.py docs/examples/local_inspector.py` | Passed (2 files) | Passed (2 files) |
| Format | `poetry run ruff format --check src/ tests/ scripts/ docs/examples/` | Passed | Passed |
| Lint | `poetry run ruff check src/ tests/ scripts/ docs/examples/` | Passed | Passed |
| Locked metadata | `poetry check --lock` | Passed | Passed |
| Distribution | `poetry build` | Passed | Passed |
| Installed wheel | `poetry run python scripts/validate_distribution.py` | Passed | Passed |

The 16 inspector cases compare snapshots and ordered transitions, check explicit
expected results, and exercise the local HTTP control boundary. The existing
20 startup-ordering cases also pass as part of each primary suite.

Self-review found no unresolved actionable code finding. Public-content review
covered every proposed file and the screenshot: synthetic data, original example
code, no credentials, private operational content, or machine-specific paths.
These checks do not constitute independent human review. The screenshot records
the recovery journey; the guide states the browser-validation limits.

<h1 align="center">XState for Python</h1>

<p align="center">
  <strong>Python statecharts with ordinary functions, typed data, and explicit lifecycles.</strong>
</p>

<p align="center">
  <a href="https://github.com/JovaniPink/xstate-python/actions/workflows/pull_request.yaml"><img alt="Tests and code quality" src="https://github.com/JovaniPink/xstate-python/actions/workflows/pull_request.yaml/badge.svg"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.13%2B-blue">
  <img alt="Status" src="https://img.shields.io/badge/status-alpha%20(0.7.1)-orange">
  <a href="./LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-green"></a>
</p>

Describe which events can change application state, keep domain data in context,
and connect Python actions and actor logic where work needs to happen. Choose
pure transition evaluation, a synchronous service, an asyncio service, or a
machine actor according to the resources your application needs to own.

The library has **zero runtime dependencies** and requires **Python 3.13+**.
The current source candidate is alpha `0.7.1`. This project builds on
[Stately's Python implementation](https://github.com/statelyai/xstate-python),
[XState](https://github.com/statelyai/xstate), and the
[W3C SCXML execution algorithm](https://www.w3.org/TR/scxml/#AlgorithmforSCXMLInterpretation).

**Start here:** [Getting started](docs/getting-started.md) ·
[Runnable examples](docs/examples/README.md) ·
[Documentation](docs/README.md) · [Contributing](CONTRIBUTING.md)

## Install From Source

Distribution ownership and publication are tracked in
[issue #57](https://github.com/JovaniPink/xstate-python/issues/57). Install this
repository's source to use the APIs documented here; `pip install xstate` is
not the installation path for this source candidate.

On macOS or Linux, with Python 3.13 or newer:

```bash
git clone https://github.com/JovaniPink/xstate-python.git
cd xstate-python
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
python docs/examples/typed_context.py
```

The [installation guide](docs/getting-started.md#install-the-library-and-examples)
includes Windows commands, how to record the source revision, and the separate
Poetry environment for contributors. The examples and their JSON/SCXML files
live in the checkout; they are not installed as library modules by the wheel.

## Your First Statechart

This complete program needs only the installed library:

```python
from xstate import Machine

review = Machine(
    {
        "id": "review",
        "initial": "draft",
        "states": {
            "draft": {"on": {"SUBMIT": "reviewing"}},
            "reviewing": {
                "on": {"APPROVE": "approved", "REQUEST_CHANGES": "draft"}
            },
            "approved": {"type": "final"},
        },
    },
    strict=True,
)

state = review.initial_state
print(state.value)
state = review.transition(state, "SUBMIT")
print(state.value)
state = review.transition(state, "APPROVE")
print(state.value)
assert state.status == "done"
```

Output:

```text
draft
reviewing
approved
```

`Machine.transition(snapshot, event)` computes the next snapshot. Guards and
assignments run during that computation; deferred side-effect actions need a
runtime to execute them. Keep guards and assignment functions free of external
side effects. The [getting-started guide](docs/getting-started.md) explains the
vocabulary, adds a stateful actor, and points to complete Python examples.

## Choose An Execution API

| What your application needs | Start with | Complete example |
| --- | --- | --- |
| Compute the next state from a snapshot and event | `Machine.transition` | [SCXML toggle](docs/examples/scxml_toggle.py) |
| Synchronous actions, subscriptions, and controlled time | `interpret` | [Traffic intersection](docs/examples/traffic_intersection.py) |
| Awaitable machine actions | `interpret_async` | [Async workflow](docs/examples/async_workflow.py) |
| Invoked children, actor messaging, or restored machine actors | `create_actor` | [Fetch with retry](docs/examples/fetch_with_retry.py) |

`interpret_async` awaits machine actions but does not start invoked children or
route actor messages. Machine-backed `create_actor` supports invocation and
messaging through the synchronous runtime; its machine actions are synchronous.
Async child logic needs a running event loop on its starting thread. Read the
[runtime capability matrix](docs/concepts/runtimes.md) before combining these
capabilities.

## Learn Through Runnable Examples

The [example catalog](docs/examples/README.md) provides commands, expected
results, and the contract each example demonstrates. The offline programs use
scripted data or fake resources and need no model API keys.

| Start with | What you learn |
| --- | --- |
| [Typed context](docs/examples/typed_context.py) | Frozen dataclass context, typed events, named guards and assignments, and computed final output |
| [Revision gate](docs/examples/revision_gate.py) · [walkthrough](docs/guides/revision-gate.md) | Bind CI/review evidence to a code revision, invalidate it on a new revision, and hand off a serialized snapshot |
| [Fetch with retry](docs/examples/fetch_with_retry.py) | JSON configuration, promise actors, success/failure events, and deterministic retry timing |
| [Snapshot resume](docs/examples/snapshot_resume.py) | Serialize, stop, restore, and continue a machine actor with explicit recovery limits |
| [Docking controller](docs/examples/docking_controller.py) · [guide](docs/concepts/controllers.md) | Typed application methods, resource ownership, cancellation, timeouts, and Markdown traces |
| [Local inspector](docs/concepts/local-inspector.md) | Explore the fake fetch workflow in a loopback browser UI and inspect its microsteps |

The revision gate is an executable example of chart policy. It does not contact
GitHub, authenticate review events, merge code, or provide crash-safe effect
recovery. The [product notes](docs/PRODUCT.md) and
[contribution-workflow issue](https://github.com/JovaniPink/xstate-python/issues/56)
keep those application responsibilities and evidence requirements explicit.

## Capabilities And Boundaries

- Hierarchical, parallel, final, and history states; guards; context assignments;
  entry/exit actions; raised events; eventless transitions; delayed transitions.
- Typed handler arguments, immutable dataclass context adapters, snapshot
  queries, and a strict `setup(...).create_machine(...)` authoring path.
- Promise, callback, and observable actor logic; child invocation and messaging.
- Snapshot serialization, microstep inspection, and dependency-free Mermaid export.
- XState-shaped data-only JSON and a focused safe SCXML import subset.

The [compatibility contract](docs/concepts/xstate-compatibility.md) compares
behavior with pinned XState **5.33.4** and records exact known differences.
Loading a JSON chart does not establish full XState or Stately-export parity.
SCXML import supports the documented safe expression subset, not general
JavaScript evaluation.

A snapshot records chart data; it does not persist event queues, timer deadlines,
child progress, or external effects. Applications own those recovery decisions.
See [persistence](docs/concepts/persistence.md) and
[action failure semantics](docs/concepts/runtimes.md#action-failure-and-external-completion).

## Documentation Map

- **Learn:** [Getting started](docs/getting-started.md),
  [machines and implementations](docs/concepts/machines-and-implementations.md),
  [typing](docs/concepts/typing.md), and [examples](docs/examples/README.md).
- **Integrate:** [Runtime choices](docs/concepts/runtimes.md),
  [actors](docs/concepts/actors.md), [controllers](docs/concepts/controllers.md),
  [persistence](docs/concepts/persistence.md), and [SCXML](docs/concepts/scxml.md).
- **Inspect:** [Local inspector](docs/concepts/local-inspector.md),
  [tracing](docs/concepts/runtimes.md#bounded-execution-and-microstep-traces), and
  [comparison with other libraries](docs/comparison.md).
- **Understand direction:** [Product notes](docs/PRODUCT.md),
  [roadmap](docs/plans/statechart-workflow-roadmap.md), and
  [Pythonic agent-workflow research](docs/plans/pythonic-agent-workflows-research.md).

## Developing

```bash
poetry install

# Primary suite
poetry run python -m pytest tests/ --ignore=tests/test_scxml.py

# Type checking
poetry run mypy src/xstate/

# Formatting and linting
poetry run ruff format --check src/ tests/ scripts/ docs/examples/
poetry run ruff check src/ tests/ scripts/ docs/examples/

# Build and test the installed wheel
poetry check --lock
poetry build
poetry run python scripts/validate_distribution.py
```

### Continuous integration

Pull requests run the primary suite on Python 3.13 and 3.14, the stable SCXML
smoke subset, and the complete formatting, lint, type, metadata, build, and
installed-wheel checks. The test suite enforces the 90% coverage floor directly,
so pull-request acceptance does not depend on an external coverage service.

The workflows use the Node-runtime-v7 releases of checkout and setup-python.
Release and manual preflight workflows use the same checkout and Python setup
majors so validation and publication do not drift onto deprecated action
runtimes.

### Release preflight

Before creating the GitHub Release for `0.7.1`, run the local preflight from
the target commit:

```bash
poetry run python scripts/release_preflight.py v0.7.1
```

The preflight verifies the expected tag against `pyproject.toml`, checks that
`HEAD` matches `origin/master`, runs the release quality gates, and builds the
distribution without publishing. Pass `--target-ref` or `--master-ref` if the
release target needs to be checked against different refs.

The GitHub **Release Preflight** workflow exposes the same dry run through
`workflow_dispatch`. It checks out `master`, defaults to `v0.7.1`, and calls
the same script without publishing. The GitHub Release workflow is fail-closed:
it delegates validation to the same script but can publish only when the
repository variable `PYPI_PUBLISH_ENABLED` is explicitly set to `true`, the
token is configured, and ownership of the chosen PyPI project has been verified.
Creating a tag or GitHub Release is not publication authorization.

## Related Projects

- [XState](https://github.com/statelyai/xstate)
- [Stately](https://stately.ai/editor)
- [python-statemachine](https://github.com/fgmacedo/python-statemachine)
- [transitions](https://github.com/pytransitions/transitions)
- [Sismic](https://github.com/AlexandreDecan/sismic)

## License

[MIT](./LICENSE)

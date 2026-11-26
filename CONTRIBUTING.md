# Contributing

Thanks for helping shape `xstate-python`. The project is still alpha, so small,
well-tested changes with clear intent are especially valuable.

## Branches

Start from the branch your work is stacked on. For ordinary work, branch from
`master`; for follow-up work on an open PR, branch from that PR branch.

Use descriptive branch names without a `codex/` prefix, for example:

```bash
git checkout master
git pull
git checkout -b docs-current-state-refresh
```

## Development Setup

```bash
poetry install
```

The package uses a `src/` layout and Python 3.13+. The core runtime has no
dependencies; development tools are managed through Poetry.

## Checks

Run the primary suite before opening a PR:

```bash
poetry run python -m pytest tests/ --ignore=tests/test_scxml.py
```

Run type checking and linting:

```bash
poetry run mypy src/xstate/
poetry run mypy --explicit-package-bases docs/examples/typed_context.py docs/examples/revision_gate.py
poetry run ruff format --check src/ tests/ scripts/ docs/examples/
poetry run ruff check src/ tests/ scripts/ docs/examples/
poetry check --lock
poetry build
poetry run python scripts/validate_distribution.py
```

SCXML changes use the checked-in, provenance-preserving fixture subset:

```bash
poetry run python -m pytest tests/test_scxml.py
```

The configured SCXML suite must pass in full. It is a focused subset and does
not yet claim broad W3C datamodel or executable-content conformance.

Changes to the advertised XState subset also run the separate compatibility
contract with Node **24.22.1**:

```bash
npm ci --prefix tests/compatibility/xstate_v5 --ignore-scripts --no-audit --no-fund
poetry run python scripts/compare_xstate_v5.py
```

The JavaScript dependency is pinned to XState **5.33.4** in its own lockfile.
The ordinary Python suite and installed package do not require Node. Read the
[compatibility guide](docs/concepts/xstate-compatibility.md) before adding a
fixture or changing a known divergence: a newly matching case must become a
required parity case, and an unexplained difference must fail the contract.

## Public Examples And Documentation

The [example catalog](docs/examples/README.md) is the public learning path.
Keep its commands and expected results aligned with the programs:

- Make the default demonstration deterministic and self-contained. Use recorded
  inputs and fake resources so readers can run it without credentials or paid
  services.
- Load adjacent JSON or XML fixtures relative to `__file__`, so the example
  works when launched from a different directory.
- Use public APIs and ordinary Python domain types. Explain the behavior the
  example demonstrates and the responsibilities it leaves to its caller.
- Stop actors and interpreters in `finally` blocks when the example owns them.
  Keep external resource cleanup explicit.
- Add behavioral tests for the example's decisions and failure cases. Update
  the catalog and relevant concept guide with a command and observable result.

The subprocess suite discovers noninteractive `docs/examples/*.py` programs
and runs each from a temporary working directory against the current source.
The installed-wheel validator runs the same collection against the isolated
wheel, without `PYTHONPATH` or runtime dependencies. `local_inspector.py` is an
interactive server with its own lifecycle tests; it is excluded from those
one-shot runs.

```bash
poetry run python -m pytest tests/test_examples.py tests/test_typed_context_example.py tests/test_revision_gate_example.py
poetry build
poetry run python scripts/validate_distribution.py
```

The [reader setup](docs/getting-started.md) uses a normal virtual environment
and `python -m pip install .`; the locked Poetry environment above is for
contributors. Validate copyable Python snippets in the reader environment as
well as running the developer checks. Examples and guides live in the source
checkout; installing the wheel alone does not install the documentation tree.

## Pull Requests

Please keep PRs focused:

- Explain what changed and why.
- Mention compatibility impact, especially public API or snapshot behavior.
- Include the exact checks you ran and their results.
- Keep generated/cache files out of commits.
- Avoid staging local agent context files such as `AGENTS.md`.

For stacked work, make the PR base the branch it depends on and call out the
stack order in the PR body.

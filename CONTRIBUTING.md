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

## Pull Requests

Please keep PRs focused:

- Explain what changed and why.
- Mention compatibility impact, especially public API or snapshot behavior.
- Include the exact checks you ran and their results.
- Keep generated/cache files out of commits.
- Avoid staging local agent context files such as `AGENTS.md`.

For stacked work, make the PR base the branch it depends on and call out the
stack order in the PR body.

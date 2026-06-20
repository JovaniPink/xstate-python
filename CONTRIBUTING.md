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
poetry run ruff format --check src/ tests/
poetry run ruff check src/ tests/
```

SCXML changes need the SCXML test framework:

```bash
git submodule update --init
poetry run python -m pytest tests/test_scxml.py
```

The current known full-SCXML gap is the `more-parallel` conformance group.
Do not treat those existing failures as caused by unrelated docs or tooling
changes.

## Pull Requests

Please keep PRs focused:

- Explain what changed and why.
- Mention compatibility impact, especially public API or snapshot behavior.
- Include the exact checks you ran and their results.
- Keep generated/cache files out of commits.
- Avoid staging local agent context files such as `AGENTS.md`.

For stacked work, make the PR base the branch it depends on and call out the
stack order in the PR body.

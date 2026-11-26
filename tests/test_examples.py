"""Smoke tests for the canonical runnable examples."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "docs" / "examples"


@pytest.mark.parametrize(
    "example",
    [
        path
        for path in sorted(EXAMPLES.glob("*.py"))
        # The interactive HTTP server has a dedicated lifecycle test suite.
        if path.name != "local_inspector.py"
    ],
    ids=lambda path: path.name,
)
def test_documented_example_runs(example: Path, tmp_path: Path) -> None:
    env = os.environ.copy()
    # Exercise this checkout, even when the test runner lives in another venv.
    env["PYTHONPATH"] = str(ROOT / "src")
    # Changing cwd must not lose the repository's branch-coverage configuration
    # when pytest-cov instruments child Python processes.
    env["COVERAGE_RCFILE"] = str(ROOT / "pyproject.toml")
    result = subprocess.run(
        [sys.executable, str(example)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr or result.stdout

"""Smoke tests for the canonical runnable examples."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "example",
    [
        "traffic_intersection.py",
        "fetch_with_retry.py",
        "async_workflow.py",
        "snapshot_resume.py",
    ],
)
def test_documented_example_runs(example: str) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "docs" / "examples" / example)],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout

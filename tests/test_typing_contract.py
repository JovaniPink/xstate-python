from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TYPING = ROOT / "tests" / "typing"


def run_mypy(fixture: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--strict",
            "--show-error-codes",
            str(TYPING / fixture),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    "fixture", ["positive.py", "compatibility.py", "controller_positive.py"]
)
def test_valid_typing_contracts(fixture: str) -> None:
    result = run_mypy(fixture)
    assert result.returncode == 0, result.stdout + result.stderr


def test_invalid_typing_contracts_are_rejected() -> None:
    result = run_mypy("negative.py")
    output = result.stdout + result.stderr

    assert result.returncode != 0
    for expected in (
        'Argument 2 to "transition" of "Machine"',
        'Argument 1 to "send" of "Interpreter"',
        'expression has type "Context", variable has type "str"',
        'expression has type "Output | None", variable has type "str"',
        'variable has type "GuardHandler[Context, IncrementEvent, Output]"',
        'variable has type "OutputHandler[Context, IncrementEvent, Output]"',
        'Argument 2 to "Event"',
        'TypedDict item "maxIterations" has type "int"',
        'Argument "max_iterations" to "Machine"',
        'Argument "inspect" to "interpret"',
        'variable has type "State[str, IncrementEvent, Output]"',
        'TypedDict item "type" has type "Literal[\'INCREMENT\']"',
        'variable has type "ActorSnapshot[Output',
    ):
        assert expected in output


def test_invalid_controller_facade_arguments_are_rejected() -> None:
    result = run_mypy("controller_negative.py")
    output = result.stdout + result.stderr
    assert result.returncode != 0
    for expected in (
        'Argument 1 to "start" of "DockingController"',
        'Argument 1 to "tick" of "DockingController"',
        'Argument 1 to "advance_time" of "DockingController"',
        'expression has type "Phase", variable has type "int"',
        'variable has type "str"',
    ):
        assert expected in output

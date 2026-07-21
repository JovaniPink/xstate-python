#!/usr/bin/env python3
"""Install the built wheel in isolation and exercise its public runtime."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import tomllib
import venv
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
DIST = ROOT / "dist"

SMOKE_TEST = """
import os
from importlib.metadata import version
from importlib.resources import files

from xstate import Machine, create_actor
from xstate.scxml import scxml_to_machine

expected = os.environ["EXPECTED_XSTATE_VERSION"]
assert version("xstate") == expected
assert files("xstate").joinpath("py.typed").is_file()
assert callable(scxml_to_machine)

machine = Machine({
    "id": "wheel-smoke",
    "initial": "idle",
    "states": {
        "idle": {"on": {"START": "running"}},
        "running": {},
    },
})
actor = create_actor(machine).start()
actor.send("START")
assert actor.get_snapshot().matches("running")
actor.stop()
print(f"installed xstate {expected} wheel smoke passed")
"""


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr, flush=True)
    raise SystemExit(1)


def project_version() -> str:
    with PYPROJECT.open("rb") as pyproject:
        version = tomllib.load(pyproject).get("project", {}).get("version")
    if not isinstance(version, str):
        fail("pyproject.toml is missing [project].version")
    return version


def built_wheel(version: str) -> Path:
    wheel = DIST / f"xstate-{version}-py3-none-any.whl"
    if not wheel.is_file():
        fail(f"expected built wheel {wheel}; run 'poetry build' first")
    return wheel


def run_checked(command: Sequence[str], *, cwd: Path, env: dict[str, str]) -> None:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode == 0:
        if completed.stdout:
            print(completed.stdout.strip(), flush=True)
        return

    details = (completed.stderr or completed.stdout).strip()
    if details:
        print(details, file=sys.stderr, flush=True)
    fail(f"command failed with exit code {completed.returncode}: {' '.join(command)}")


def validate_distribution() -> None:
    version = project_version()
    wheel = built_wheel(version)

    with tempfile.TemporaryDirectory(prefix="xstate-wheel-") as temp_dir:
        temp = Path(temp_dir)
        environment = temp / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )

        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env["PYTHONNOUSERSITE"] = "1"
        env["EXPECTED_XSTATE_VERSION"] = version

        run_checked(
            (
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-deps",
                "--no-index",
                str(wheel),
            ),
            cwd=temp,
            env=env,
        )
        run_checked(
            (str(python), "-c", SMOKE_TEST),
            cwd=temp,
            env=env,
        )


if __name__ == "__main__":
    validate_distribution()

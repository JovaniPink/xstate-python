#!/usr/bin/env python3
"""Local release preflight checks for xstate-python."""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr, flush=True)
    raise SystemExit(1)


def capture(command: Sequence[str]) -> str:
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        fail(f"command not found: {command[0]}")
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout).strip()
        if details:
            fail(f"{shlex.join(command)} failed:\n{details}")
        fail(f"{shlex.join(command)} failed with exit code {exc.returncode}")
    return completed.stdout.strip()


def run(label: str, command: Sequence[str]) -> None:
    print(f"\n==> {label}", flush=True)
    print(f"+ {shlex.join(command)}", flush=True)
    try:
        completed = subprocess.run(command, cwd=ROOT, check=False)
    except FileNotFoundError:
        fail(f"command not found: {command[0]}")
    if completed.returncode != 0:
        fail(f"{label} failed with exit code {completed.returncode}")


def git_commit(ref: str) -> str:
    try:
        return capture(("git", "rev-list", "-n", "1", ref))
    except SystemExit:
        fail(
            f"could not resolve git ref {ref!r}. "
            "Fetch the ref first or pass --target-ref/--master-ref explicitly."
        )


def project_version() -> str:
    with PYPROJECT.open("rb") as pyproject:
        data = tomllib.load(pyproject)
    version = data.get("project", {}).get("version")
    if not isinstance(version, str):
        fail("pyproject.toml is missing [project].version")
    return version


def verify_release_target(expected_tag: str, target_ref: str, master_ref: str) -> None:
    version = project_version()
    project_tag = f"v{version}"
    if expected_tag != project_tag:
        fail(
            f"expected tag {expected_tag!r} does not match "
            f"pyproject.toml version {version!r}; expected {project_tag!r}."
        )

    target_commit = git_commit(target_ref)
    master_commit = git_commit(master_ref)
    if target_commit != master_commit:
        fail(
            f"target ref {target_ref!r} points at {target_commit}, "
            f"but {master_ref!r} is {master_commit}."
        )

    print(
        f"Release target verified: {expected_tag} "
        f"({target_ref} -> {target_commit[:12]}) matches {master_ref}.",
        flush=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the local release preflight before publishing to PyPI."
    )
    parser.add_argument(
        "expected_tag",
        help="Release tag expected from pyproject.toml, for example v0.7.0.",
    )
    parser.add_argument(
        "--target-ref",
        default="HEAD",
        help="Git ref intended for the release tag. Defaults to HEAD.",
    )
    parser.add_argument(
        "--master-ref",
        default="origin/master",
        help="Master ref the release target must match. Defaults to origin/master.",
    )
    args = parser.parse_args(argv)

    verify_release_target(args.expected_tag, args.target_ref, args.master_ref)

    steps: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("Check package metadata", ("poetry", "check", "--lock")),
        (
            "Run tests",
            (
                "poetry",
                "run",
                "python",
                "-m",
                "pytest",
                "tests/",
                "--ignore=tests/test_scxml.py",
            ),
        ),
        (
            "Run SCXML smoke suite",
            (
                "poetry",
                "run",
                "python",
                "-m",
                "pytest",
                "tests/test_scxml.py",
                "-m",
                "scxml_ci",
            ),
        ),
        (
            "Check formatting",
            (
                "poetry",
                "run",
                "ruff",
                "format",
                "--check",
                "src/",
                "tests/",
                "docs/examples/",
            ),
        ),
        (
            "Run lint",
            (
                "poetry",
                "run",
                "ruff",
                "check",
                "src/",
                "tests/",
                "docs/examples/",
            ),
        ),
        ("Run type checks", ("poetry", "run", "mypy", "src/xstate/")),
        ("Build distribution", ("poetry", "build")),
    )
    for label, command in steps:
        run(label, command)

    print("\nRelease preflight passed. Review dist/ before publishing.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

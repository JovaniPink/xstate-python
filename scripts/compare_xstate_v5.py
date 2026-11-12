"""Compare real Python and JS runtimes with independently authored observations.

Install the development-only reference with npm ci in
tests/compatibility/xstate_v5, then run this script using Python 3.13+.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
REFERENCE = ROOT / "tests" / "compatibility" / "xstate_v5"
# A previously installed package must never substitute for the checkout under test.
sys.path.insert(0, str(SOURCE))

import xstate  # noqa: E402
from xstate import (  # noqa: E402
    HandlerArgs,
    Machine,
    SimulatedClock,
    assign,
    create_actor,
    from_callback,
    raise_,
)


def validate_fixtures(fixtures: Any) -> None:
    """Reject vacuous or ambiguous corpora before either runtime executes."""
    if not isinstance(fixtures, list) or not fixtures:
        raise ValueError("fixtures must be a non-empty list")
    ids: set[str] = set()
    for index, fixture in enumerate(fixtures):
        if not isinstance(fixture, dict):
            raise ValueError(f"fixture[{index}] must be an object")
        name = fixture.get("id")
        if not isinstance(name, str) or not name:
            raise ValueError(f"fixture[{index}] needs a non-empty string id")
        if name in ids:
            raise ValueError(f"duplicate fixture id: {name}")
        ids.add(name)
        commands = fixture.get("commands")
        if not isinstance(commands, list) or not commands:
            raise ValueError(f"{name}: commands must be a non-empty list")
        for key in ("expected", "expected_python"):
            if key == "expected_python" and key not in fixture:
                continue
            expected = fixture.get(key)
            if not isinstance(expected, list) or len(expected) != len(commands):
                raise ValueError(
                    f"{name}: {key} must contain one observation per command "
                    f"({len(commands)}); end an error scenario at its failing command"
                )
            for step, observation in enumerate(expected):
                if not isinstance(observation, dict):
                    raise ValueError(f"{name}: {key}[{step}] must be an object")
                if observation.get("errors") and step != len(commands) - 1:
                    raise ValueError(
                        f"{name}: {key}[{step}] fails before the last command"
                    )


def run_python(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    """Observe actual actor commands; do not simulate transition selection."""
    clock = SimulatedClock()
    actions: list[dict[str, Any]] = []
    children: list[dict[str, Any]] = []
    generation = 0

    def record(args: HandlerArgs) -> None:
        event = args.event
        payload = (
            event.data
            if event is not None and isinstance(event.data, dict)
            else {"type": event.name}
            if event is not None
            else None
        )
        actions.append(
            deepcopy(
                {
                    "time": clock.now(),
                    "context": args.context,
                    "event": payload,
                    "params": args.params,
                }
            )
        )

    def worker(**kwargs: Any) -> Any:
        nonlocal generation
        generation += 1
        current = generation
        children.append(
            {
                "time": clock.now(),
                "kind": "start",
                "generation": current,
                "input": deepcopy(kwargs["input"]),
            }
        )

        def cleanup() -> None:
            children.append(
                {"time": clock.now(), "kind": "stop", "generation": current}
            )

        return cleanup

    machine = Machine(
        deepcopy(fixture["chart"]),
        actions={
            "record": record,
            "increment": assign({"n": lambda args: args.context["n"] + 1}),
            "raiseInner": raise_("INNER"),
        },
        guards={"allowed": lambda args: args.event.data.get("allow") is True},
        delays=fixture.get("delays", {}),
        actors={"worker": from_callback(worker)},
    )
    actor = create_actor(machine, clock=clock)
    steps = []
    try:
        for command in fixture["commands"]:
            actions.clear()
            children.clear()
            errors = []
            try:
                match command["type"]:
                    case "start":
                        actor.start()
                    case "send":
                        actor.send(deepcopy(command["event"]))
                    case "advance":
                        clock.increment(command["ms"])
                    case other:
                        raise ValueError(f"Unknown command: {other}")
            except Exception as error:
                errors.append({"type": type(error).__name__, "message": str(error)})
            snapshot = actor.get_snapshot()
            steps.append(
                deepcopy(
                    {
                        "time": clock.now(),
                        "value": snapshot.value,
                        "context": snapshot.context,
                        "status": snapshot.status,
                        "output": snapshot.output,
                        "actions": actions,
                        "children": {
                            "ids": list(actor.children),
                            "events": children,
                        },
                        "errors": errors,
                    }
                )
            )
            if errors:
                break
        return steps
    finally:
        actor.stop()


def first_difference(expected: Any, actual: Any, path: str = "") -> str | None:
    """Name the first exact field mismatch without sorting observed sequences."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        if expected.keys() != actual.keys():
            return f"{path}.keys expected={list(expected)!r} actual={list(actual)!r}"
        for key, value in expected.items():
            found = first_difference(value, actual[key], f"{path}.{key}")
            if found is not None:
                return found
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return f"{path}.length expected={len(expected)} actual={len(actual)}"
        for index, (left, right) in enumerate(zip(expected, actual, strict=True)):
            found = first_difference(left, right, f"{path}[{index}]")
            if found is not None:
                return found
    elif expected != actual or isinstance(expected, bool) != isinstance(actual, bool):
        return f"{path} expected={expected!r} actual={actual!r}"
    return None


def check_fixture(
    fixture: dict[str, Any],
    python: list[dict[str, Any]],
    javascript: list[dict[str, Any]],
) -> list[str]:
    """Both runtimes must meet their own oracle; known gaps are exact contracts."""
    failures = []
    known = fixture.get("known_difference")
    expected_js = fixture["expected"]
    expected_python = fixture.get("expected_python", expected_js)
    if bool(known) != (expected_python != expected_js):
        failures.append(
            f"{fixture['id']}: known-difference metadata and oracles disagree"
        )
    for runtime, expected, actual in (
        ("Python", expected_python, python),
        ("XState", expected_js, javascript),
    ):
        for index in range(max(len(expected), len(actual))):
            left = expected[index] if index < len(expected) else "<no observation>"
            right = actual[index] if index < len(actual) else "<no observation>"
            mismatch = first_difference(left, right, "snapshot")
            if mismatch:
                failures.append(
                    f"{fixture['id']} command[{index}] {runtime}: {mismatch}"
                )
    if known and python == javascript:
        failures.append(
            f"{fixture['id']}: unexpected parity; review and promote this known gap"
        )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=REFERENCE / "fixtures.json")
    args = parser.parse_args()
    fixtures = json.loads(args.fixtures.read_text())
    try:
        validate_fixtures(fixtures)
    except ValueError as error:
        parser.error(str(error))
    module_path = Path(xstate.__file__).resolve()
    if not module_path.is_relative_to(SOURCE):
        parser.error(
            f"Python imported {module_path}, expected the checkout at {SOURCE}"
        )
    source_version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"][
        "version"
    ]
    try:
        reference = subprocess.run(
            ["node", str(REFERENCE / "run.cjs"), str(args.fixtures.resolve())],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        detail = (
            error.stderr
            if isinstance(error, subprocess.CalledProcessError)
            else str(error)
        )
        print(f"Reference failed: {detail}", file=sys.stderr)
        return 1
    data = json.loads(reference.stdout)
    versions = (
        f"Python {platform.python_version()} / xstate-python {source_version}; "
        f"Node {data['node']} / XState {data['xstate']}"
    )
    print(versions)
    print(f"Python source: {module_path}")
    failures = []
    for fixture in fixtures:
        try:
            python = run_python(fixture)
        except Exception as error:
            failures.append(f"{fixture['id']} Python setup failed: {error!r}")
            continue
        problems = check_fixture(fixture, python, data["results"][fixture["id"]])
        failures.extend(problems)
        if not problems:
            kind = "KNOWN DIFFERENCE" if fixture.get("known_difference") else "PARITY"
            print(f"{kind}: {fixture['id']} ({len(python)} commands)")
    for failure in failures:
        print(f"FAIL [{versions}] {failure}", file=sys.stderr)
    print(f"Checked {len(fixtures)} fixtures; {len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

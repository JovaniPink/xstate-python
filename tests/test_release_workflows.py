from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

RELEASE_GATE_COMMANDS = (
    "poetry check --lock",
    "pytest tests/",
    "pytest tests/test_scxml.py",
    "ruff format --check",
    "ruff check",
    "mypy src/xstate/",
    "poetry build",
    "scripts/validate_distribution.py",
)


def normalized_workflow(name: str) -> str:
    return " ".join((WORKFLOWS / name).read_text().split())


def assert_delegates_to_preflight(workflow: str, invocation: str) -> None:
    assert workflow.count("scripts/release_preflight.py") == 1
    assert invocation in workflow
    for command in RELEASE_GATE_COMMANDS:
        assert command not in workflow


def test_release_workflow_delegates_validation_to_preflight_script() -> None:
    workflow = normalized_workflow("release.yaml")

    assert_delegates_to_preflight(
        workflow,
        (
            'poetry run python scripts/release_preflight.py "$RELEASE_TAG" '
            '--target-ref "$RELEASE_TAG" --master-ref origin/master'
        ),
    )
    assert "run: poetry publish" in workflow


def test_manual_preflight_runs_v070_dry_run_against_master() -> None:
    workflow = normalized_workflow("release_preflight.yaml")

    assert "workflow_dispatch:" in workflow
    assert "default: v0.7.0" in workflow
    assert "ref: master" in workflow
    assert "fetch-depth: 0" in workflow
    assert_delegates_to_preflight(
        workflow,
        (
            "poetry run python scripts/release_preflight.py "
            '"${{ inputs.expected_tag }}" --target-ref HEAD '
            "--master-ref origin/master"
        ),
    )
    assert "poetry publish" not in workflow

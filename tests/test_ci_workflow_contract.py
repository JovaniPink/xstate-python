from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def read_workflow(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_all_python_workflows_use_current_action_runtime_majors() -> None:
    workflow_text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(WORKFLOWS.glob("*.yaml"))
    )

    assert "actions/checkout@v4" not in workflow_text
    assert "actions/setup-python@v5" not in workflow_text
    assert workflow_text.count("actions/checkout@v7") == 5
    assert workflow_text.count("actions/setup-python@v7") == 5


def test_coverage_gate_does_not_depend_on_an_external_upload() -> None:
    workflow = read_workflow("pull_request.yaml")

    assert "--cov --cov-report=xml" in workflow
    assert "codecov/codecov-action" not in workflow
    assert "id-token: write" not in workflow

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def read_workflow(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_all_python_workflows_pin_action_revisions() -> None:
    workflow_text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(WORKFLOWS.glob("*.yaml"))
    )

    checkout = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
    setup_python = "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"
    assert workflow_text.count(checkout) == 5
    assert workflow_text.count(setup_python) == 5
    assert "actions/checkout@v" not in workflow_text
    assert "actions/setup-python@v" not in workflow_text
    assert "submodules:" not in workflow_text


def test_coverage_gate_does_not_depend_on_an_external_upload() -> None:
    workflow = read_workflow("pull_request.yaml")

    assert "--cov --cov-report=xml" in workflow
    assert "codecov/codecov-action" not in workflow
    assert "id-token: write" not in workflow

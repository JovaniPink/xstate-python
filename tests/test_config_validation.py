import json
from pathlib import Path

import pytest

from xstate import (
    InvalidConfigError,
    Machine,
    create_actor,
    find_config_issues,
    from_callback,
    setup,
)


def _cfg(**state_extra):
    return {"id": "m", "initial": "a", "states": {"a": state_extra, "b": {}}}


def test_valid_config_has_no_issues():
    config = {
        "id": "m",
        "initial": "a",
        "context": {"n": 0},
        "options": {"maxIterations": 10},
        "states": {
            "a": {
                "description": "start",
                "entry": ["x"],
                "on": {"GO": [{"target": "b", "guard": "g", "meta": {}}]},
                "always": {"target": "b", "in": "#m.b"},
                "after": {100: "b"},
                "invoke": {
                    "id": "i",
                    "src": "s",
                    "onDone": "b",
                    "onError": {"target": "b"},
                },
            },
            "b": {"type": "final", "output": {}},
        },
    }
    assert find_config_issues(config) == []


def test_unknown_keys_reported_with_paths_in_document_order():
    config = _cfg(on={"X": {"target": "b", "bogus": 1}}, nope=True)
    config["typo"] = 1
    issues = find_config_issues(config)
    assert [(i.code, i.path, i.key) for i in issues] == [
        ("unknown_key", "config", "typo"),
        ("unknown_key", "config.states.a", "nope"),
        ("unknown_key", "config.states.a.on['X']", "bogus"),
    ]


def test_reenter_is_an_accepted_transition_key():
    config = _cfg(on={"X": [{"target": "a", "reenter": True}]})
    assert find_config_issues(config) == []
    Machine(config, strict=True)


def test_compatibility_corpus_charts_pass_strict_validation():
    corpus = Path(__file__).parent / "compatibility" / "xstate_v5" / "fixtures.json"
    fixtures = json.loads(corpus.read_text())
    assert fixtures
    for fixture in fixtures:
        assert find_config_issues(fixture["chart"]) == [], fixture["id"]


def test_invoke_keys_checked():
    config = _cfg(
        invoke={"src": "s", "autoForward": True, "onDone": {"target": "b", "x": 1}}
    )
    codes = {(i.code, i.key) for i in find_config_issues(config)}
    assert codes == {("unsupported_key", "autoForward"), ("unknown_key", "x")}


def test_default_machine_still_ignores_unknown_keys():
    Machine(_cfg(on={"X": {"target": "b", "bogus": True}}, nope=1))


def test_strict_machine_raises_listing_all_issues():
    config = _cfg(on={"X": {"target": "b", "bogus": True}}, nope=1)
    with pytest.raises(InvalidConfigError) as exc:
        Machine(config, strict=True)
    assert "bogus" in str(exc.value) and "nope" in str(exc.value)


def test_strict_machine_accepts_valid_config():
    Machine(_cfg(on={"X": "b"}), strict=True)


def test_setup_api_is_strict():
    with pytest.raises(InvalidConfigError):
        setup().create_machine(_cfg(nope=1))


@pytest.mark.parametrize("as_list", [False, True])
def test_invoke_system_id_is_reported_as_unsupported(as_list):
    invocation = {"id": "worker", "src": "workerLogic", "systemId": "alias"}
    config = _cfg(invoke=[invocation] if as_list else invocation)

    issues = find_config_issues(config)

    assert [(issue.code, issue.path, issue.key) for issue in issues] == [
        ("unsupported_key", "config.states.a.invoke[0]", "systemId")
    ]
    assert "does not implement yet" in issues[0].message


@pytest.mark.parametrize("via_setup", [False, True])
def test_strict_construction_rejects_invoke_system_id_with_path(via_setup):
    config = _cfg(invoke={"src": "workerLogic", "systemId": "alias"})

    with pytest.raises(InvalidConfigError) as exc:
        if via_setup:
            setup().create_machine(config)
        else:
            Machine(config, strict=True)

    assert "config.states.a.invoke[0]" in str(exc.value)
    assert "'systemId'" in str(exc.value)
    assert "does not implement yet" in str(exc.value)


def test_default_machine_ignores_system_id_and_keeps_invoke_id():
    machine = Machine(
        _cfg(invoke={"id": "worker", "src": "workerLogic", "systemId": "alias"}),
        actors={"workerLogic": from_callback(lambda: None)},
    )
    actor = create_actor(machine).start()
    try:
        child = actor.children["worker"]
        assert actor.system.get("worker") is child
        assert actor.system.get("alias") is None
    finally:
        actor.stop()

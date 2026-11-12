import pytest

from xstate import InvalidConfigError, Machine, find_config_issues, setup


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


def test_reenter_is_reported_as_unsupported_not_unknown():
    config = _cfg(on={"X": [{"target": "a", "reenter": True}]})
    (issue,) = find_config_issues(config)
    assert issue.code == "unsupported_key"
    assert issue.path == "config.states.a.on['X'][0]"
    assert "reenter" in issue.message


def test_invoke_keys_checked():
    config = _cfg(
        invoke={"src": "s", "autoForward": True, "onDone": {"target": "b", "x": 1}}
    )
    codes = {(i.code, i.key) for i in find_config_issues(config)}
    assert codes == {("unsupported_key", "autoForward"), ("unknown_key", "x")}


def test_default_machine_still_ignores_unknown_keys():
    Machine(_cfg(on={"X": {"target": "b", "reenter": True}}, nope=1))


def test_strict_machine_raises_listing_all_issues():
    config = _cfg(on={"X": {"target": "b", "reenter": True}}, nope=1)
    with pytest.raises(InvalidConfigError) as exc:
        Machine(config, strict=True)
    assert "reenter" in str(exc.value) and "nope" in str(exc.value)


def test_strict_machine_accepts_valid_config():
    Machine(_cfg(on={"X": "b"}), strict=True)


def test_setup_api_is_strict():
    with pytest.raises(InvalidConfigError):
        setup().create_machine(_cfg(nope=1))

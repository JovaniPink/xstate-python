"""JSON reentry and the explicit legacy/SCXML transition boundary."""

import pytest

from xstate import InvalidConfigError, Machine, create_actor, from_callback, interpret
from xstate.scxml import scxml_to_machine


@pytest.mark.parametrize("value", [None, 0, 1, "true", [], {}])
def test_reenter_requires_a_boolean(value):
    with pytest.raises(InvalidConfigError, match="reenter.*must be a boolean"):
        Machine(
            {
                "id": "invalid-reentry",
                "initial": "idle",
                "states": {
                    "idle": {"on": {"GO": {"target": "idle", "reenter": value}}}
                },
            }
        )


@pytest.mark.parametrize("reenter", [False, True])
def test_explicit_reenter_takes_precedence_over_legacy_type(reenter):
    effects = []
    machine = Machine(
        {
            "id": "explicit-reentry",
            "initial": "idle",
            "states": {
                "idle": {
                    "entry": lambda: effects.append("entry"),
                    "exit": lambda: effects.append("exit"),
                    "on": {
                        "GO": {
                            "target": "idle",
                            "type": "external" if not reenter else "internal",
                            "reenter": reenter,
                        }
                    },
                }
            },
        }
    )
    service = interpret(machine).start()
    try:
        effects.clear()
        service.send("GO")
        assert effects == (["exit", "entry"] if reenter else [])
    finally:
        service.stop()


@pytest.mark.parametrize("kind,count", [(None, 2), ("external", 2), ("internal", 1)])
def test_scxml_preserves_external_default_and_explicit_internal(tmp_path, kind, count):
    attribute = "" if kind is None else f' type="{kind}"'
    source = tmp_path / "lifecycle.scxml"
    source.write_text(
        f'''<scxml xmlns="http://www.w3.org/2005/07/scxml" initial="parent"
  datamodel="ecmascript">
  <datamodel><data id="entries" expr="0"/></datamodel>
  <state id="parent" initial="first">
    <onentry><assign location="entries" expr="entries + 1"/></onentry>
    <transition event="MOVE" target="second"{attribute}/>
    <state id="first"/><state id="second"/>
  </state>
</scxml>''',
        encoding="utf-8",
    )
    machine = scxml_to_machine(source)
    state = machine.transition(machine.initial_state, "MOVE")
    assert state.value == {"parent": "second"}
    assert state.context == {"entries": count}


def test_scxml_rejects_unknown_transition_type(tmp_path):
    source = tmp_path / "invalid.scxml"
    source.write_text(
        '<scxml initial="idle"><state id="idle">'
        '<transition event="GO" target="idle" type="unknown"/>'
        "</state></scxml>",
        encoding="utf-8",
    )
    with pytest.raises(InvalidConfigError, match="transition type"):
        scxml_to_machine(source)


def test_default_self_transition_preserves_parallel_sibling_configuration():
    machine = Machine(
        {
            "id": "parallel-retention",
            "type": "parallel",
            "states": {
                "a": {"on": {"TOUCH": "a"}},
                "b": {
                    "initial": "first",
                    "states": {"first": {"on": {"NEXT": "second"}}, "second": {}},
                },
            },
        }
    )
    state = machine.transition(machine.initial_state, "NEXT")
    state = machine.transition(state, "TOUCH")
    assert state.value == {"a": {}, "b": "second"}
    assert (
        len(
            [node for node in state.configuration if node.parent is machine.states["b"]]
        )
        == 1
    )


def test_transient_invocation_never_starts_and_final_generation_starts_once():
    events = []

    def worker(*, input):  # noqa: A002 - actor input contract
        events.append(f"{input}.start")
        return lambda: events.append(f"{input}.stop")

    machine = Machine(
        {
            "id": "transient-invocation",
            "initial": "a",
            "states": {
                "a": {
                    "entry": lambda: events.append("a.entry"),
                    "exit": lambda: events.append("a.exit"),
                    "invoke": {"id": "a-worker", "src": "worker", "input": "a"},
                    "on": {"GO": "b"},
                },
                "b": {
                    "entry": lambda: events.append("b.entry"),
                    "exit": lambda: events.append("b.exit"),
                    "invoke": {"id": "b-worker", "src": "worker", "input": "b"},
                    "always": "a",
                },
            },
        },
        actors={"worker": from_callback(worker)},
    )
    actor = create_actor(machine).start()
    actor.subscribe(lambda _state: events.append("notify"))
    try:
        original = actor.children["a-worker"]
        events.clear()
        actor.send("GO")
        assert events == [
            "a.exit",
            "b.entry",
            "b.exit",
            "a.entry",
            "a.stop",
            "a.start",
            "notify",
        ]
        assert actor.children["a-worker"] is not original
        assert actor.system.get("b-worker") is None
    finally:
        actor.stop()


def test_parallel_completion_does_not_choose_an_arbitrary_child_output():
    machine = Machine(
        {
            "id": "parallel-output",
            "type": "parallel",
            "states": {
                "a": {"type": "final", "output": "A"},
                "b": {"type": "final", "output": "B"},
            },
        }
    )
    done = machine.initial_state
    assert done.status == "done"
    assert done.output is None
    assert machine.state_from(done.value).output is None


def test_final_root_completes_without_a_parent_state():
    effects = []
    machine = Machine(
        {
            "id": "final-root",
            "type": "final",
            "output": "accepted",
            "entry": lambda: effects.append("entry"),
            "exit": lambda: effects.append("exit"),
        }
    )
    service = interpret(machine).start()
    assert service.status == "done"
    assert service.state.output == "accepted"
    assert effects == ["entry", "exit"]
    service.send("AGAIN")
    service.start()
    assert effects == ["entry", "exit"]

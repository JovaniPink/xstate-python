import warnings
from pathlib import Path

import pytest

from xstate.exceptions import InvalidConfigError
from xstate.scxml import scxml_to_machine


def write_scxml(tmp_path: Path, content: str) -> Path:
    source = tmp_path / "machine.scxml"
    source.write_text(content, encoding="utf-8")
    return source


def test_imported_condition_uses_canonical_guard_without_warnings(
    tmp_path: Path,
) -> None:
    source = write_scxml(
        tmp_path,
        """<?xml version="1.0"?>
<scxml xmlns="http://www.w3.org/2005/07/scxml" initial="off">
  <state id="off">
    <transition event="TOGGLE" cond="true &amp;&amp; !false" target="on"/>
  </state>
  <state id="on"/>
</scxml>
""",
    )

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        machine = scxml_to_machine(source)
        state = machine.transition(machine.initial_state, "TOGGLE")

    transition = machine.config["states"]["off"]["on"]["TOGGLE"][0]
    assert "guard" in transition
    assert "cond" not in transition
    assert state.matches("on")


def test_imported_multi_target_transition_accepts_xml_whitespace(
    tmp_path: Path,
) -> None:
    source = write_scxml(
        tmp_path,
        """<?xml version="1.0"?>
<scxml xmlns="http://www.w3.org/2005/07/scxml" initial="source">
  <state id="source">
    <transition event="GO" target="left_on   right_on"/>
  </state>
  <parallel id="active">
    <state id="left" initial="left_off">
      <state id="left_off"/>
      <state id="left_on"/>
    </state>
    <state id="right" initial="right_off">
      <state id="right_off"/>
      <state id="right_on"/>
    </state>
  </parallel>
</scxml>
""",
    )

    machine = scxml_to_machine(source)
    state = machine.transition(machine.initial_state, "GO")

    assert state.value == {
        "active": {
            "left": "left_on",
            "right": "right_on",
        }
    }


def test_imported_assign_subset_preserves_parallel_entry_exit_order() -> None:
    source = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "scxml"
        / "more-parallel"
        / "test10b.scxml"
    )
    machine = scxml_to_machine(source)

    state = machine.initial_state
    assert state.context == {"x": 2}

    state = machine.transition(state, "t1")
    assert state.value == {"p": {"a": {}, "b": {}}}
    assert state.context == {"x": 4}

    state = machine.transition(state, "t2")
    assert state.matches("c")
    assert state.context == {"x": 6}

    state = machine.transition(state, "t3")
    assert state.matches("d")
    assert state.context == {"x": 6}


def test_imported_integer_guard_does_not_treat_boolean_as_integer(
    tmp_path: Path,
) -> None:
    source = write_scxml(
        tmp_path,
        """<scxml xmlns="http://www.w3.org/2005/07/scxml" datamodel="ecmascript">
  <datamodel>
    <data id="x" expr="0"/>
  </datamodel>
  <state id="waiting">
    <transition event="GO" cond="x === 1" target="done"/>
  </state>
  <state id="done"/>
</scxml>""",
    )
    machine = scxml_to_machine(source)
    state = machine.initial_state
    state.context["x"] = True

    state = machine.transition(state, "GO")

    assert state.matches("waiting")


def test_import_defaults_to_first_state(tmp_path: Path) -> None:
    source = write_scxml(
        tmp_path,
        """<scxml xmlns="http://www.w3.org/2005/07/scxml">
  <state id="first"/>
  <state id="second"/>
</scxml>
""",
    )

    assert scxml_to_machine(source).initial_state.matches("first")


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("<state id='wrong-root'/>", "Expected an <scxml> document root"),
        (
            "<scxml xmlns='http://www.w3.org/2005/07/scxml'/>",
            "must contain at least one",
        ),
        (
            """<scxml xmlns="http://www.w3.org/2005/07/scxml">
  <state/>
</scxml>""",
            "requires a non-empty 'id' attribute",
        ),
        (
            """<scxml xmlns="http://www.w3.org/2005/07/scxml">
  <state id="left">
    <state id="same"/>
  </state>
  <state id="right">
    <state id="same"/>
  </state>
</scxml>""",
            "Duplicate SCXML state id 'same'",
        ),
        (
            """<scxml xmlns="http://www.w3.org/2005/07/scxml">
  <state id="only">
    <onentry><raise/></onentry>
  </state>
</scxml>""",
            "requires a non-empty 'event' attribute",
        ),
        (
            """<scxml xmlns="http://www.w3.org/2005/07/scxml">
  <state id="only">
    <transition event="GO" cond="count &gt; 0"/>
  </state>
</scxml>""",
            "Unsupported SCXML JavaScript cond expression",
        ),
    ],
)
def test_import_rejects_invalid_scxml(
    tmp_path: Path,
    content: str,
    message: str,
) -> None:
    source = write_scxml(tmp_path, content)

    with pytest.raises(InvalidConfigError, match=message):
        scxml_to_machine(source)


def test_import_wraps_malformed_xml(tmp_path: Path) -> None:
    source = write_scxml(tmp_path, "<scxml><state id='open'></scxml>")

    with pytest.raises(InvalidConfigError, match="Invalid SCXML XML"):
        scxml_to_machine(source)


@pytest.mark.parametrize(
    ("data_expression", "assign_location", "assign_expression", "condition", "message"),
    [
        ("1 + 1", "x", "x + 1", "true", "<data> expression"),
        ("0", "x", "x + 2", "true", "<assign> expression"),
        ("0", "x", "1 + x", "true", "<assign> expression"),
        ("0", "x.count", "x.count + 1", "true", "<assign> location"),
        ("0", "missing", "missing + 1", "true", "<assign> location"),
        ("0", "x", "x + 1", "x == 1", "cond expression"),
        ("0", "x", "x + 1", "x === 1 &amp;&amp; true", "cond expression"),
        ("0", "x", "x + 1", "event === 1", "not declared"),
    ],
)
def test_import_rejects_expressions_outside_assign_subset(
    tmp_path: Path,
    data_expression: str,
    assign_location: str,
    assign_expression: str,
    condition: str,
    message: str,
) -> None:
    source = write_scxml(
        tmp_path,
        f"""<scxml xmlns="http://www.w3.org/2005/07/scxml" datamodel="ecmascript">
  <datamodel>
    <data id="x" expr="{data_expression}"/>
  </datamodel>
  <state id="only">
    <onentry>
      <assign location="{assign_location}" expr="{assign_expression}"/>
    </onentry>
    <transition event="GO" cond="{condition}"/>
  </state>
</scxml>""",
    )

    with pytest.raises(InvalidConfigError, match=message):
        scxml_to_machine(source)

import pytest

from xstate import InvalidConfigError, Machine, to_mermaid


def _alias(state_id):
    return "s_" + state_id.encode("utf-8").hex()


def test_to_mermaid_exports_state_diagram():
    machine = Machine(
        {
            "id": "chart",
            "initial": "idle",
            "states": {
                "idle": {
                    "on": {
                        "START": {
                            "target": "active",
                            "guard": lambda _context, _event: True,
                        }
                    }
                },
                "active": {
                    "initial": "pending",
                    "states": {
                        "pending": {"on": {"FINISH": "done"}},
                        "done": {"type": "final"},
                    },
                },
            },
        }
    )

    diagram = to_mermaid(machine)

    assert diagram.startswith("stateDiagram-v2\n")
    assert f"  [*] --> {_alias('chart.idle')}\n" in diagram
    assert f'  state "idle" as {_alias("chart.idle")}\n' in diagram
    assert f'  state "active" as {_alias("chart.active")}\n' in diagram
    assert f"  state {_alias('chart.active')} {{\n" in diagram
    assert f"    [*] --> {_alias('chart.active.pending')}\n" in diagram
    assert (
        f"  {_alias('chart.idle')} --> {_alias('chart.active')}: START [guard]\n"
        in diagram
    )
    assert (
        f"  {_alias('chart.active.pending')} --> "
        f"{_alias('chart.active.done')}: FINISH\n" in diagram
    )


def test_to_mermaid_keeps_targetless_transitions_as_comments():
    machine = Machine(
        {
            "id": "chart",
            "initial": "idle",
            "states": {
                "idle": {"on": {"PING": {"actions": "trackPing"}}},
            },
        }
    )

    assert f"%% {_alias('chart.idle')} handles PING" in to_mermaid(machine)


def test_to_mermaid_does_not_emit_parallel_root_initial_target():
    machine = Machine(
        {
            "id": "cross",
            "type": "parallel",
            "states": {
                "a": {"initial": "a1", "states": {"a1": {}}},
                "b": {"initial": "b1", "states": {"b1": {}}},
            },
        }
    )

    diagram = to_mermaid(machine)

    assert f"  [*] --> {_alias('cross')}\n" not in diagram
    assert f'  state "a" as {_alias("cross.a")}\n' in diagram
    assert f"    [*] --> {_alias('cross.a.a1')}\n" in diagram
    assert f'  state "b" as {_alias("cross.b")}\n' in diagram
    assert f"    [*] --> {_alias('cross.b.b1')}\n" in diagram


def test_to_mermaid_preserves_distinct_aliases_for_similar_ids():
    machine = Machine(
        {
            "id": "m",
            "initial": "a-b",
            "states": {
                "a-b": {"on": {"GO": "a_b"}},
                "a_b": {},
            },
        }
    )

    diagram = to_mermaid(machine)

    dashed = _alias("m.a-b")
    underscored = _alias("m.a_b")
    assert dashed != underscored
    assert f'state "a-b" as {dashed}' in diagram
    assert f'state "a_b" as {underscored}' in diagram
    assert f"{dashed} --> {underscored}: GO" in diagram


def test_snapshot_annotations_preserve_legacy_output_and_initial_arrows():
    machine = Machine(
        {"id": "flat", "initial": "a", "states": {"a": {"on": {"GO": "b"}}, "b": {}}}
    )
    legacy = to_mermaid(machine)
    assert legacy == (
        "stateDiagram-v2\n"
        "  [*] --> s_666c61742e61\n"
        '  state "a" as s_666c61742e61\n'
        '  state "b" as s_666c61742e62\n'
        "  s_666c61742e61 --> s_666c61742e62: GO\n"
    )
    assert to_mermaid(machine, snapshot=None) == legacy
    snapshot = machine.transition(machine.initial_state, "GO")
    assert to_mermaid(machine, snapshot=snapshot) == legacy.replace(
        'state "b"', 'state "b [active]"'
    )


@pytest.mark.parametrize("parallel", [False, True])
def test_snapshot_annotations_include_nested_and_parallel_captions(parallel):
    config = {
        "id": "nested",
        "initial": "left",
        "states": {
            "left": {"initial": "a", "states": {"a": {}, "b": {}}},
            "right": {"initial": "c", "states": {"c": {}, "d": {}}},
        },
    }
    if parallel:
        config.pop("initial")
        config["type"] = "parallel"
    machine = Machine(config)
    snapshot = machine.initial_state
    legacy = to_mermaid(machine)
    expected = legacy
    for caption in ["left", "a", "right", "c"] if parallel else ["left", "a"]:
        expected = expected.replace(f'state "{caption}"', f'state "{caption} [active]"')
    assert to_mermaid(machine, snapshot=snapshot) == expected
    assert to_mermaid(machine) == legacy


def test_snapshot_annotations_reject_foreign_nodes_even_with_matching_ids():
    config = {"id": "same", "initial": "a", "states": {"a": {}}}
    machine, other = Machine(config), Machine(config)
    with pytest.raises(InvalidConfigError, match="does not belong"):
        to_mermaid(machine, snapshot=other.initial_state)

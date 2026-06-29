from xstate import Machine, to_mermaid


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

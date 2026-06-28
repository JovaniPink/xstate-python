from xstate import Machine, to_mermaid


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
    assert "  [*] --> s_chart_idle\n" in diagram
    assert '  state "idle" as s_chart_idle\n' in diagram
    assert '  state "active" as s_chart_active\n' in diagram
    assert "  state s_chart_active {\n" in diagram
    assert "    [*] --> s_chart_active_pending\n" in diagram
    assert "  s_chart_idle --> s_chart_active: START [guard]\n" in diagram
    assert "  s_chart_active_pending --> s_chart_active_done: FINISH\n" in diagram


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

    assert "%% s_chart_idle handles PING" in to_mermaid(machine)

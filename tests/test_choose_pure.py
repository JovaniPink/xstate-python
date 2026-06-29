"""Tests for choose() and pure() higher-order actions (0.7.0).

`choose` runs the actions of the first branch whose guard passes.
`pure` builds a list of actions from (context, event) with no side effects of
its own. Both expand into sub-actions executed in order through the engine.
"""

import pytest

from xstate import (
    Machine,
    and_,
    assign,
    choose,
    create_actor,
    pure,
    raise_,
)

# ---------------------------------------------------------------------------
# choose — branch selection
# ---------------------------------------------------------------------------


def _size_machine(guards=None):
    return Machine(
        {
            "id": "m",
            "initial": "a",
            "context": {"n": 5},
            "states": {
                "a": {
                    "on": {
                        "GO": {
                            "target": "b",
                            "actions": [
                                choose(
                                    [
                                        {
                                            "guard": lambda c, e: c["n"] > 10,
                                            "actions": assign({"size": "big"}),
                                        },
                                        {
                                            "guard": "isMedium",
                                            "actions": assign({"size": "medium"}),
                                        },
                                        {"actions": assign({"size": "small"})},
                                    ]
                                )
                            ],
                        }
                    }
                },
                "b": {},
            },
        },
        guards=guards or {"isMedium": lambda c, e: c["n"] > 3},
    )


def test_choose_picks_middle_branch():
    actor = create_actor(_size_machine()).start()  # n == 5
    actor.send("GO")
    assert actor.get_snapshot().context["size"] == "medium"


def test_choose_picks_first_branch():
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "context": {"n": 99},
            "states": {
                "a": {
                    "on": {
                        "GO": {
                            "target": "b",
                            "actions": [
                                choose(
                                    [
                                        {
                                            "guard": lambda c, e: c["n"] > 10,
                                            "actions": assign({"size": "big"}),
                                        },
                                        {"actions": assign({"size": "small"})},
                                    ]
                                )
                            ],
                        }
                    }
                },
                "b": {},
            },
        }
    )
    actor = create_actor(machine).start()
    actor.send("GO")
    assert actor.get_snapshot().context["size"] == "big"


def test_choose_falls_through_to_default_branch():
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "context": {"n": 1},
            "states": {
                "a": {
                    "on": {
                        "GO": {
                            "target": "b",
                            "actions": [
                                choose(
                                    [
                                        {
                                            "guard": lambda c, e: c["n"] > 10,
                                            "actions": assign({"size": "big"}),
                                        },
                                        {"actions": assign({"size": "small"})},
                                    ]
                                )
                            ],
                        }
                    }
                },
                "b": {},
            },
        }
    )
    actor = create_actor(machine).start()
    actor.send("GO")
    assert actor.get_snapshot().context["size"] == "small"


def test_choose_runs_only_first_match():
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "context": {"hits": 0},
            "states": {
                "a": {
                    "on": {
                        "GO": {
                            "target": "b",
                            "actions": [
                                choose(
                                    [
                                        {
                                            "guard": lambda c, e: True,
                                            "actions": assign(
                                                {"hits": lambda c, e: c["hits"] + 1}
                                            ),
                                        },
                                        {
                                            "guard": lambda c, e: True,
                                            "actions": assign(
                                                {"hits": lambda c, e: c["hits"] + 10}
                                            ),
                                        },
                                    ]
                                )
                            ],
                        }
                    }
                },
                "b": {},
            },
        }
    )
    actor = create_actor(machine).start()
    actor.send("GO")
    assert actor.get_snapshot().context["hits"] == 1


def test_choose_no_match_runs_nothing():
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "context": {"touched": False},
            "states": {
                "a": {
                    "on": {
                        "GO": {
                            "target": "b",
                            "actions": [
                                choose(
                                    [
                                        {
                                            "guard": lambda c, e: False,
                                            "actions": assign({"touched": True}),
                                        }
                                    ]
                                )
                            ],
                        }
                    }
                },
                "b": {},
            },
        }
    )
    actor = create_actor(machine).start()
    actor.send("GO")
    assert actor.get_snapshot().context["touched"] is False


def test_choose_with_composable_guard():
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "context": {"x": True, "y": True},
            "states": {
                "a": {
                    "on": {
                        "GO": {
                            "target": "b",
                            "actions": [
                                choose(
                                    [
                                        {
                                            "guard": and_("isX", "isY"),
                                            "actions": assign({"both": True}),
                                        },
                                        {"actions": assign({"both": False})},
                                    ]
                                )
                            ],
                        }
                    }
                },
                "b": {},
            },
        },
        guards={"isX": lambda c, e: c["x"], "isY": lambda c, e: c["y"]},
    )
    actor = create_actor(machine).start()
    actor.send("GO")
    assert actor.get_snapshot().context["both"] is True


def test_choose_in_entry_action():
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "context": {"n": 7},
            "states": {
                "a": {
                    "entry": [
                        choose(
                            [
                                {
                                    "guard": lambda c, e: c["n"] > 5,
                                    "actions": assign({"label": "high"}),
                                },
                                {"actions": assign({"label": "low"})},
                            ]
                        )
                    ]
                },
            },
        }
    )
    actor = create_actor(machine).start()
    assert actor.get_snapshot().context["label"] == "high"


def test_choose_unknown_guard_raises():
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "context": {},
            "states": {
                "a": {
                    "on": {
                        "GO": {
                            "actions": [choose([{"guard": "missing", "actions": []}])]
                        }
                    }
                },
            },
        }
    )
    actor = create_actor(machine).start()
    with pytest.raises(Exception, match="missing"):
        actor.send("GO")


def test_choose_invalid_branch_raises():
    from xstate.exceptions import InvalidConfigError

    with pytest.raises(InvalidConfigError, match="each choose branch must be a dict"):
        Machine(
            {
                "id": "m",
                "initial": "a",
                "states": {"a": {"entry": [choose(["not-a-dict"])]}},
            }
        )


# ---------------------------------------------------------------------------
# pure — dynamic action lists
# ---------------------------------------------------------------------------


def test_pure_returns_single_action():
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "context": {"items": [1, 2, 3]},
            "states": {
                "a": {
                    "on": {
                        "GO": {
                            "target": "b",
                            "actions": [
                                pure(lambda c, e: assign({"total": sum(c["items"])}))
                            ],
                        }
                    }
                },
                "b": {},
            },
        }
    )
    actor = create_actor(machine).start()
    actor.send("GO")
    assert actor.get_snapshot().context["total"] == 6


def test_pure_returns_list_of_actions():
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "context": {"a": 0, "b": 0},
            "states": {
                "a": {
                    "on": {
                        "GO": {
                            "target": "b",
                            "actions": [
                                pure(
                                    lambda c, e: [
                                        assign({"a": 1}),
                                        assign({"b": 2}),
                                    ]
                                )
                            ],
                        }
                    }
                },
                "b": {},
            },
        }
    )
    actor = create_actor(machine).start()
    actor.send("GO")
    snap = actor.get_snapshot()
    assert snap.context["a"] == 1
    assert snap.context["b"] == 2


def test_pure_returns_none_runs_nothing():
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "context": {"touched": False},
            "states": {
                "a": {
                    "on": {
                        "GO": {
                            "target": "b",
                            "actions": [pure(lambda c, e: None)],
                        }
                    }
                },
                "b": {},
            },
        }
    )
    actor = create_actor(machine).start()
    actor.send("GO")
    assert actor.get_snapshot().context["touched"] is False


def test_pure_side_effect_action_runs():
    calls = []
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "context": {},
            "states": {
                "a": {
                    "on": {
                        "GO": {
                            "target": "b",
                            "actions": [pure(lambda c, e: "notify")],
                        }
                    }
                },
                "b": {},
            },
        },
        actions={"notify": lambda: calls.append("notified")},
    )
    actor = create_actor(machine).start()
    actor.send("GO")
    assert calls == ["notified"]


def test_pure_can_raise_event():
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "context": {"chained": False},
            "states": {
                "a": {
                    "on": {
                        "GO": {
                            "target": "b",
                            "actions": [pure(lambda c, e: raise_("NEXT"))],
                        }
                    }
                },
                "b": {
                    "on": {
                        "NEXT": {
                            "target": "c",
                            "actions": assign({"chained": True}),
                        }
                    }
                },
                "c": {},
            },
        }
    )
    actor = create_actor(machine).start()
    actor.send("GO")
    snap = actor.get_snapshot()
    assert snap.value == "c"
    assert snap.context["chained"] is True


def test_pure_in_entry_action():
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "context": {"ready": False},
            "states": {
                "a": {"entry": [pure(lambda c, e: assign({"ready": True}))]},
            },
        }
    )
    actor = create_actor(machine).start()
    assert actor.get_snapshot().context["ready"] is True

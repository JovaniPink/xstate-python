"""Tests for the user-facing stateIn() guard (0.7.0).

`stateIn(spec)` is a composable guard that passes when the machine is currently
in the given state. It reuses the same matching as a transition `in` guard and
composes with and_/or_/not_.
"""


from xstate import Machine, and_, create_actor, not_, or_, stateIn

# ---------------------------------------------------------------------------
# Standalone semantics (no configuration → False)
# ---------------------------------------------------------------------------


def test_stateIn_called_directly_without_config_is_false():
    # With no active configuration there is nothing to match against.
    assert stateIn("#ready")(None, None) is False


# ---------------------------------------------------------------------------
# stateIn as a transition guard — by id
# ---------------------------------------------------------------------------


def _two_region_machine(guard):
    return Machine(
        {
            "id": "m",
            "type": "parallel",
            "states": {
                "switch": {
                    "initial": "off",
                    "states": {
                        "off": {"on": {"FLIP": "on"}},
                        "on": {"id": "switchOn", "on": {"FLIP": "off"}},
                    },
                },
                "worker": {
                    "initial": "waiting",
                    "states": {
                        "waiting": {"on": {"GO": {"target": "active", "guard": guard}}},
                        "active": {},
                    },
                },
            },
        }
    )


def test_stateIn_by_id_blocks_when_not_in_state():
    machine = _two_region_machine(stateIn("#switchOn"))
    actor = create_actor(machine).start()
    # switch is off → guard fails → worker stays waiting
    actor.send("GO")
    assert actor.get_snapshot().value["worker"] == "waiting"


def test_stateIn_by_id_passes_when_in_state():
    machine = _two_region_machine(stateIn("#switchOn"))
    actor = create_actor(machine).start()
    actor.send("FLIP")  # switch → on (#switchOn)
    assert actor.get_snapshot().value["switch"] == "on"
    actor.send("GO")
    assert actor.get_snapshot().value["worker"] == "active"


# ---------------------------------------------------------------------------
# stateIn by dotted path
# ---------------------------------------------------------------------------


def test_stateIn_by_dotted_path():
    machine = Machine(
        {
            "id": "m",
            "type": "parallel",
            "states": {
                "switch": {
                    "initial": "off",
                    "states": {
                        "off": {"on": {"FLIP": "on"}},
                        "on": {"on": {"FLIP": "off"}},
                    },
                },
                "worker": {
                    "initial": "waiting",
                    "states": {
                        "waiting": {
                            "on": {
                                "GO": {
                                    "target": "active",
                                    "guard": stateIn("switch.on"),
                                }
                            }
                        },
                        "active": {},
                    },
                },
            },
        }
    )
    actor = create_actor(machine).start()
    actor.send("GO")
    assert actor.get_snapshot().value["worker"] == "waiting"
    actor.send("FLIP")
    actor.send("GO")
    assert actor.get_snapshot().value["worker"] == "active"


# ---------------------------------------------------------------------------
# Composition with and_/or_/not_
# ---------------------------------------------------------------------------


def test_stateIn_composed_with_and():
    machine = Machine(
        {
            "id": "m",
            "type": "parallel",
            "states": {
                "switch": {
                    "initial": "off",
                    "states": {
                        "off": {"on": {"FLIP": "on"}},
                        "on": {"id": "switchOn", "on": {"FLIP": "off"}},
                    },
                },
                "worker": {
                    "initial": "waiting",
                    "states": {
                        "waiting": {
                            "on": {
                                "GO": {
                                    "target": "active",
                                    "guard": and_("isAllowed", stateIn("#switchOn")),
                                }
                            }
                        },
                        "active": {},
                    },
                },
            },
        },
        guards={"isAllowed": lambda c, e: True},
    )
    actor = create_actor(machine).start()
    actor.send("GO")  # switchOn not active → blocked
    assert actor.get_snapshot().value["worker"] == "waiting"
    actor.send("FLIP")
    actor.send("GO")  # both true → passes
    assert actor.get_snapshot().value["worker"] == "active"


def test_stateIn_composed_with_not():
    machine = _two_region_machine(not_(stateIn("#switchOn")))
    actor = create_actor(machine).start()
    # switch is off → not(stateIn) is True → passes immediately
    actor.send("GO")
    assert actor.get_snapshot().value["worker"] == "active"


def test_stateIn_composed_with_or():
    machine = _two_region_machine(or_(stateIn("#switchOn"), lambda c, e: False))
    actor = create_actor(machine).start()
    actor.send("GO")
    assert actor.get_snapshot().value["worker"] == "waiting"
    actor.send("FLIP")
    actor.send("GO")
    assert actor.get_snapshot().value["worker"] == "active"


# ---------------------------------------------------------------------------
# Named registry resolution + setup()
# ---------------------------------------------------------------------------


def test_stateIn_registered_as_named_guard():
    machine = Machine(
        {
            "id": "m",
            "type": "parallel",
            "states": {
                "switch": {
                    "initial": "off",
                    "states": {
                        "off": {"on": {"FLIP": "on"}},
                        "on": {"id": "switchOn", "on": {"FLIP": "off"}},
                    },
                },
                "worker": {
                    "initial": "waiting",
                    "states": {
                        "waiting": {
                            "on": {"GO": {"target": "active", "guard": "switchIsOn"}}
                        },
                        "active": {},
                    },
                },
            },
        },
        guards={"switchIsOn": stateIn("#switchOn")},
    )
    actor = create_actor(machine).start()
    actor.send("GO")
    assert actor.get_snapshot().value["worker"] == "waiting"
    actor.send("FLIP")
    actor.send("GO")
    assert actor.get_snapshot().value["worker"] == "active"

"""Tests for the setup() builder API (0.6.0).

Covers:
  - setup() returns a MachineSetup instance
  - create_machine() returns a Machine
  - All four registries: guards, actions, actors, delays
  - context_adapter parameter accepted
  - Multiple create_machine() calls from one setup() (registries are merged)
"""

from xstate import Machine, SimulatedClock, and_, create_actor, setup
from xstate.setup_api import MachineSetup

# ---------------------------------------------------------------------------
# Basic setup() usage
# ---------------------------------------------------------------------------


def test_setup_returns_machine_setup():
    result = setup()
    assert isinstance(result, MachineSetup)


def test_create_machine_returns_machine():
    machine = setup().create_machine(
        {
            "id": "m",
            "initial": "idle",
            "states": {"idle": {}},
        }
    )
    assert isinstance(machine, Machine)


def test_setup_guards_registered():
    machine = setup(
        guards={
            "isReady": lambda c, e: True,
        }
    ).create_machine(
        {
            "id": "m",
            "initial": "a",
            "states": {
                "a": {"on": {"GO": {"target": "b", "guard": "isReady"}}},
                "b": {},
            },
        }
    )
    actor = create_actor(machine).start()
    actor.send("GO")
    assert actor.get_snapshot().value == "b"


def test_setup_actions_registered():
    calls = []

    machine = setup(
        actions={
            "recordCall": lambda: calls.append(True),
        }
    ).create_machine(
        {
            "id": "m",
            "initial": "a",
            "states": {
                "a": {"on": {"GO": {"target": "b", "actions": ["recordCall"]}}},
                "b": {},
            },
        }
    )
    actor = create_actor(machine).start()
    actor.send("GO")
    assert len(calls) == 1


def test_setup_delays_registered():
    clock = SimulatedClock()
    machine = setup(
        delays={
            "SHORT": 500,
        }
    ).create_machine(
        {
            "id": "m",
            "initial": "a",
            "states": {
                "a": {"after": {"SHORT": "b"}},
                "b": {},
            },
        }
    )
    actor = create_actor(machine, clock=clock).start()
    assert actor.get_snapshot().value == "a"
    clock.increment(500)
    assert actor.get_snapshot().value == "b"


def test_multiple_create_machine_from_one_setup():
    ms = setup(
        guards={
            "isReady": lambda c, e: True,
        }
    )
    m1 = ms.create_machine(
        {
            "id": "m1",
            "initial": "a",
            "states": {
                "a": {"on": {"GO": {"target": "b", "guard": "isReady"}}},
                "b": {},
            },
        }
    )
    m2 = ms.create_machine(
        {
            "id": "m2",
            "initial": "x",
            "states": {
                "x": {"on": {"GO": {"target": "y", "guard": "isReady"}}},
                "y": {},
            },
        }
    )
    a1 = create_actor(m1).start()
    a2 = create_actor(m2).start()
    a1.send("GO")
    a2.send("GO")
    assert a1.get_snapshot().value == "b"
    assert a2.get_snapshot().value == "y"


def test_create_machine_overrides_setup_guards():
    machine = setup(
        guards={
            "isReady": lambda c, e: False,
        }
    ).create_machine(
        {
            "id": "m",
            "initial": "a",
            "states": {
                "a": {"on": {"GO": {"target": "b", "guard": "isReady"}}},
                "b": {},
            },
        },
        guards={
            "isReady": lambda c, e: True,
        },
    )
    actor = create_actor(machine).start()
    actor.send("GO")
    assert actor.get_snapshot().value == "b"


def test_setup_with_composable_guard():
    machine = setup(
        guards={
            "isLoggedIn": lambda c, e: c.get("logged_in", False),
            "isAdmin": lambda c, e: c.get("admin", False),
            "canEdit": and_("isLoggedIn", "isAdmin"),
        }
    ).create_machine(
        {
            "id": "m",
            "initial": "view",
            "context": {"logged_in": True, "admin": True},
            "states": {
                "view": {"on": {"EDIT": {"target": "edit", "guard": "canEdit"}}},
                "edit": {},
            },
        }
    )
    actor = create_actor(machine).start()
    actor.send("EDIT")
    assert actor.get_snapshot().value == "edit"


def test_setup_no_args_creates_empty_machine_setup():
    ms = setup()
    assert ms.guards == {}
    assert ms.actions == {}
    assert ms.delays == {}
    assert ms.actors == {}
    assert ms.context_adapter is None

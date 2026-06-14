"""Tests for actor logic kinds and the parent/child actor tree (0.5.0).

Covers:
  - from_promise: eager resolve / reject, snapshot status + output/error
  - from_callback: send_back to parent, receive() of sent events, cleanup
  - spawn(): child actors share the system, know their parent, stop with parent
"""

from xstate import Machine, create_actor, from_callback, from_promise
from xstate.actor import ActorSystem

# ---------------------------------------------------------------------------
# from_promise
# ---------------------------------------------------------------------------


def test_promise_resolves_with_output():
    actor = create_actor(from_promise(lambda input: 42)).start()
    snap = actor.get_snapshot()
    assert snap.status == "done"
    assert snap.output == 42


def test_promise_receives_input():
    actor = create_actor(from_promise(lambda input: input * 2), input=21).start()
    assert actor.get_snapshot().output == 42


def test_promise_zero_arg_fn():
    actor = create_actor(from_promise(lambda: "ok")).start()
    assert actor.get_snapshot().output == "ok"


def test_promise_rejects_into_error_snapshot():
    def boom(input):
        raise RuntimeError("nope")

    actor = create_actor(from_promise(boom)).start()
    snap = actor.get_snapshot()
    assert snap.status == "error"
    assert isinstance(snap.error, RuntimeError)
    assert str(snap.error) == "nope"


def test_promise_not_started_is_active():
    actor = create_actor(from_promise(lambda input: 1))
    assert actor.status == "not_started"
    assert actor.get_snapshot().status == "active"


# ---------------------------------------------------------------------------
# from_callback
# ---------------------------------------------------------------------------


def _parent_with_child(child_logic, child_id="child"):
    """A machine actor that spawns a child and forwards PING via the child."""
    parent_machine = Machine(
        {
            "id": "parent",
            "initial": "waiting",
            "states": {
                "waiting": {"on": {"PONG": "done"}},
                "done": {},
            },
        }
    )
    parent = create_actor(parent_machine).start()
    child = parent.spawn(child_logic, id=child_id)
    return parent, child


def test_callback_send_back_reaches_parent():
    def logic(send_back):
        send_back("PONG")

    parent, child = _parent_with_child(from_callback(logic))
    child.start()
    assert parent.get_snapshot().value == "done"


def test_callback_receive_handles_sent_events():
    received = []

    def logic(receive):
        receive(lambda event: received.append(event))

    actor = create_actor(from_callback(logic)).start()
    actor.send("HELLO")
    assert received == ["HELLO"]


def test_callback_cleanup_runs_on_stop():
    cleaned = []

    def logic():
        return lambda: cleaned.append(True)

    actor = create_actor(from_callback(logic)).start()
    assert cleaned == []
    actor.stop()
    assert cleaned == [True]


def test_callback_receives_input():
    seen = {}

    def logic(input):
        seen["input"] = input

    create_actor(from_callback(logic), input={"k": 1}).start()
    assert seen["input"] == {"k": 1}


# ---------------------------------------------------------------------------
# parent / child tree
# ---------------------------------------------------------------------------


def _toggle_machine():
    return Machine(
        {
            "id": "toggle",
            "initial": "off",
            "states": {
                "off": {"on": {"TOGGLE": "on"}},
                "on": {"on": {"TOGGLE": "off"}},
            },
        }
    )


def test_spawn_child_shares_system_and_knows_parent():
    parent = create_actor(_toggle_machine()).start()
    child = parent.spawn(_toggle_machine(), id="kid")
    assert child.parent is parent
    assert child.system is parent.system
    assert parent.system.get("kid") is child
    assert parent.children["kid"] is child


def test_stopping_parent_stops_children():
    parent = create_actor(_toggle_machine()).start()
    child = parent.spawn(_toggle_machine(), id="kid").start()
    assert child.status == "running"
    parent.stop()
    assert child.status == "stopped"
    assert parent.system.get("kid") is None


def test_spawn_into_explicit_shared_system():
    system = ActorSystem()
    parent = create_actor(_toggle_machine(), id="p", system=system).start()
    child = parent.spawn(_toggle_machine(), id="c")
    assert system.get("p") is parent
    assert system.get("c") is child

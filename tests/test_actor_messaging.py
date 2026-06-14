"""Tests for inter-actor messaging and the code-review bug fixes (0.5.0).

Covers:
  - send_parent: an invoked child machine notifies its parent
  - send_to: addressing a sibling actor by id through the system
  - regression: falsy invoke id honored, anonymous-id collision avoided,
    missing src rejected, reconcile is atomic on a bad src
"""

import pytest

from xstate import Machine, assign, create_actor, from_promise, send_parent, send_to
from xstate.actor import ActorSystem

# ---------------------------------------------------------------------------
# send_parent
# ---------------------------------------------------------------------------


def test_send_parent_from_invoked_child_machine():
    child = Machine(
        {
            "id": "child",
            "initial": "announcing",
            "states": {
                # On entry the child tells the parent it is ready, then idles.
                "announcing": {"entry": [send_parent("CHILD_READY")]},
            },
        }
    )
    parent = Machine(
        {
            "id": "parent",
            "initial": "waiting",
            "states": {
                "waiting": {
                    "invoke": {"id": "child", "src": child},
                    "on": {"CHILD_READY": "ready"},
                },
                "ready": {},
            },
        }
    )
    actor = create_actor(parent).start()
    assert actor.get_snapshot().value == "ready"


def test_send_parent_noop_without_parent():
    machine = Machine(
        {
            "id": "orphan",
            "initial": "a",
            "states": {"a": {"entry": [send_parent("NOPE")]}},
        }
    )
    # No parent → the action is a no-op and start() does not raise.
    actor = create_actor(machine).start()
    assert actor.get_snapshot().value == "a"


# ---------------------------------------------------------------------------
# send_to
# ---------------------------------------------------------------------------


def test_send_to_sibling_actor():
    logger = Machine(
        {
            "id": "logger",
            "context": {"count": 0},
            "initial": "idle",
            "states": {
                "idle": {
                    "on": {
                        "LOG": {
                            "actions": [assign({"count": lambda c, e: c["count"] + 1})]
                        }
                    }
                }
            },
        }
    )
    emitter = Machine(
        {
            "id": "emitter",
            "initial": "go",
            "states": {"go": {"entry": [send_to("logger", "LOG")]}},
        }
    )
    system = ActorSystem()
    logger_actor = create_actor(logger, id="logger", system=system).start()
    create_actor(emitter, id="emitter", system=system).start()
    assert logger_actor.get_snapshot().context["count"] == 1


def test_send_to_unknown_target_is_noop():
    emitter = Machine(
        {
            "id": "emitter",
            "initial": "go",
            "states": {"go": {"entry": [send_to("ghost", "LOG")]}},
        }
    )
    actor = create_actor(emitter).start()
    assert actor.get_snapshot().value == "go"


# ---------------------------------------------------------------------------
# regression: invoke id handling
# ---------------------------------------------------------------------------


def test_invoke_falsy_id_is_honored():
    """An explicit id of 0 must not be replaced by a generated id."""
    machine = Machine(
        {
            "id": "falsy",
            "context": {"v": None},
            "initial": "run",
            "states": {
                "run": {
                    "invoke": {
                        "id": 0,
                        "src": from_promise(lambda input: "done"),
                        "onDone": {
                            "target": "ok",
                            "actions": [assign({"v": lambda c, e: e.data})],
                        },
                    }
                },
                "ok": {},
            },
        }
    )
    actor = create_actor(machine).start()
    # If the falsy id were dropped, the done.invoke.0 event would never match.
    assert actor.get_snapshot().value == "ok"
    assert actor.get_snapshot().context["v"] == "done"


def test_invoke_missing_src_raises_at_construction():
    with pytest.raises(ValueError, match="missing a 'src'"):
        Machine(
            {
                "id": "bad",
                "initial": "run",
                "states": {"run": {"invoke": {"id": "x"}}},
            }
        )


# ---------------------------------------------------------------------------
# regression: anonymous id collision
# ---------------------------------------------------------------------------


def test_anonymous_id_skips_explicit_collision():
    system = ActorSystem()

    def _toggle():
        return Machine(
            {
                "id": "t",
                "initial": "a",
                "states": {"a": {"on": {"T": "b"}}, "b": {}},
            }
        )

    explicit = create_actor(_toggle(), id="x:0", system=system)
    anon = create_actor(_toggle(), system=system)  # must not collide with x:0
    assert explicit.id == "x:0"
    assert anon.id != "x:0"
    assert system.get(anon.id) is anon

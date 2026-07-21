"""Tests for composable guard combinators (0.6.0).

Covers:
  - and_/or_/not_ standalone semantics with callable sub-guards
  - Composable guards wired into Machine transitions
  - String sub-guard resolution via machine guards registry
  - Nested combinator compositions
  - setup() + composable guards end-to-end
"""

import pytest

from xstate import HandlerArgs, Machine, and_, create_actor, not_, or_, setup

# ---------------------------------------------------------------------------
# Standalone semantics
# ---------------------------------------------------------------------------


def _true(ctx, evt):
    return True


def _false(ctx, evt):
    return False


def test_and_true_when_all_true():
    g = and_(_true, _true)
    assert g(None, None) is True


def test_and_false_when_any_false():
    g = and_(_true, _false)
    assert g(None, None) is False


def test_or_true_when_any_true():
    g = or_(_false, _true)
    assert g(None, None) is True


def test_or_false_when_all_false():
    g = or_(_false, _false)
    assert g(None, None) is False


def test_not_inverts():
    assert not_(lambda c, e: True)(None, None) is False
    assert not_(lambda c, e: False)(None, None) is True


def test_and_empty_is_true():
    g = and_()
    assert g(None, None) is True


def test_or_empty_is_false():
    g = or_()
    assert g(None, None) is False


def test_composable_guard_accepts_handler_args():
    guard = and_(lambda args: args.context["ready"])

    assert guard(HandlerArgs(context={"ready": True}, event=None)) is True


# ---------------------------------------------------------------------------
# Machine integration — callable sub-guards
# ---------------------------------------------------------------------------


def _make_machine(guard_fn):
    return Machine(
        {
            "id": "m",
            "initial": "a",
            "states": {
                "a": {"on": {"GO": {"target": "b", "guard": guard_fn}}},
                "b": {},
            },
        }
    )


def test_and_guard_in_machine_passes():
    machine = _make_machine(and_(lambda c, e: True, lambda c, e: True))
    actor = create_actor(machine).start()
    actor.send("GO")
    assert actor.get_snapshot().value == "b"


def test_and_guard_in_machine_blocks():
    machine = _make_machine(and_(lambda c, e: True, lambda c, e: False))
    actor = create_actor(machine).start()
    actor.send("GO")
    assert actor.get_snapshot().value == "a"


def test_or_guard_in_machine_passes():
    machine = _make_machine(or_(lambda c, e: False, lambda c, e: True))
    actor = create_actor(machine).start()
    actor.send("GO")
    assert actor.get_snapshot().value == "b"


def test_not_guard_in_machine_passes():
    machine = _make_machine(not_(lambda c, e: False))
    actor = create_actor(machine).start()
    actor.send("GO")
    assert actor.get_snapshot().value == "b"


def test_not_guard_in_machine_blocks():
    machine = _make_machine(not_(lambda c, e: True))
    actor = create_actor(machine).start()
    actor.send("GO")
    assert actor.get_snapshot().value == "a"


# ---------------------------------------------------------------------------
# String sub-guard resolution via machine.guards registry
# ---------------------------------------------------------------------------


def test_event_payload_does_not_replace_context_for_string_guards():
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "states": {
                "a": {
                    "on": {
                        "GO": {
                            "target": "b",
                            "guard": and_("isLoggedIn", "hasPermission"),
                        }
                    }
                },
                "b": {},
            },
        },
        guards={
            "isLoggedIn": lambda c, e: c.get("logged_in"),
            "hasPermission": lambda c, e: c.get("permission"),
        },
    )
    actor = create_actor(machine).start()
    actor.send({"type": "GO", "logged_in": True, "permission": True})
    assert actor.get_snapshot().value == "a"


def test_and_string_guards_with_context():
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "context": {"logged_in": True, "permission": True},
            "states": {
                "a": {
                    "on": {
                        "GO": {
                            "target": "b",
                            "guard": and_("isLoggedIn", "hasPermission"),
                        }
                    }
                },
                "b": {},
            },
        },
        guards={
            "isLoggedIn": lambda args: args.context.get("logged_in"),
            "hasPermission": lambda args: args.context.get("permission"),
        },
    )
    actor = create_actor(machine).start()
    actor.send("GO")
    assert actor.get_snapshot().value == "b"


def test_and_string_guards_blocked_by_missing_permission():
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "context": {"logged_in": True, "permission": False},
            "states": {
                "a": {
                    "on": {
                        "GO": {
                            "target": "b",
                            "guard": and_("isLoggedIn", "hasPermission"),
                        }
                    }
                },
                "b": {},
            },
        },
        guards={
            "isLoggedIn": lambda args: args.context.get("logged_in"),
            "hasPermission": lambda args: args.context.get("permission"),
        },
    )
    actor = create_actor(machine).start()
    actor.send("GO")
    assert actor.get_snapshot().value == "a"


def test_or_string_guards_passes_one_true():
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "context": {"a": False, "b": True},
            "states": {
                "a": {"on": {"GO": {"target": "b", "guard": or_("isA", "isB")}}},
                "b": {},
            },
        },
        guards={
            "isA": lambda c, e: c.get("a"),
            "isB": lambda c, e: c.get("b"),
        },
    )
    actor = create_actor(machine).start()
    actor.send("GO")
    assert actor.get_snapshot().value == "b"


def test_not_string_guard_inverts():
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "context": {"locked": False},
            "states": {
                "a": {"on": {"GO": {"target": "b", "guard": not_("isLocked")}}},
                "b": {},
            },
        },
        guards={
            "isLocked": lambda c, e: c.get("locked"),
        },
    )
    actor = create_actor(machine).start()
    actor.send("GO")
    assert actor.get_snapshot().value == "b"


def test_unknown_string_guard_raises_key_error():
    machine = Machine(
        {
            "id": "m",
            "initial": "a",
            "context": {},
            "states": {
                "a": {"on": {"GO": {"target": "b", "guard": and_("nonexistent")}}},
                "b": {},
            },
        },
    )
    actor = create_actor(machine).start()
    with pytest.raises(KeyError, match="nonexistent"):
        actor.send("GO")


# ---------------------------------------------------------------------------
# Nested combinators
# ---------------------------------------------------------------------------


def test_nested_and_or():
    # and_(true, or_(false, true)) => and_(true, true) => True
    g = and_(lambda c, e: True, or_(lambda c, e: False, lambda c, e: True))
    assert g(None, None) is True


def test_nested_not_and():
    # not_(and_(true, false)) => not_(False) => True
    g = not_(and_(lambda c, e: True, lambda c, e: False))
    assert g(None, None) is True


# ---------------------------------------------------------------------------
# setup() + composable guards end-to-end
# ---------------------------------------------------------------------------


def test_setup_with_composable_guards():
    machine = setup(
        guards={
            "isLoggedIn": lambda args: args.context.get("logged_in"),
            "hasPermission": lambda args: args.context.get("permission"),
            "canAccess": and_("isLoggedIn", "hasPermission"),
        }
    ).create_machine(
        {
            "id": "m",
            "initial": "a",
            "context": {"logged_in": True, "permission": True},
            "states": {
                "a": {"on": {"GO": {"target": "b", "guard": "canAccess"}}},
                "b": {},
            },
        }
    )
    actor = create_actor(machine).start()
    actor.send("GO")
    assert actor.get_snapshot().value == "b"


def test_setup_composable_guard_blocks():
    machine = setup(
        guards={
            "isLoggedIn": lambda args: args.context.get("logged_in"),
            "hasPermission": lambda args: args.context.get("permission"),
            "canAccess": and_("isLoggedIn", "hasPermission"),
        }
    ).create_machine(
        {
            "id": "m",
            "initial": "a",
            "context": {"logged_in": False, "permission": True},
            "states": {
                "a": {"on": {"GO": {"target": "b", "guard": "canAccess"}}},
                "b": {},
            },
        }
    )
    actor = create_actor(machine).start()
    actor.send("GO")
    assert actor.get_snapshot().value == "a"

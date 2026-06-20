"""Tests for the actor-model foundation (0.5.0).

Covers the v5 ``create_actor`` entry point and the actor system registry:
  - actor lifecycle (start/stop/status) delegates to the interpreter
  - send + run-to-completion through the actor
  - get_snapshot / state
  - subscriptions
  - ActorSystem: ids, get(), registration and cleanup on stop
"""

import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from xstate import Machine, SimulatedClock, create_actor
from xstate.actor import Actor, ActorSystem


def _toggle_machine():
    return Machine(
        {
            "id": "toggle",
            "initial": "inactive",
            "states": {
                "inactive": {"on": {"TOGGLE": "active"}},
                "active": {"on": {"TOGGLE": "inactive"}},
            },
        }
    )


# ---------------------------------------------------------------------------
# lifecycle
# ---------------------------------------------------------------------------


def test_create_actor_returns_unstarted_actor():
    actor = create_actor(_toggle_machine())
    assert isinstance(actor, Actor)
    assert actor.status == "not_started"


def test_start_runs_the_actor():
    actor = create_actor(_toggle_machine()).start()
    assert actor.status == "running"
    assert actor.get_snapshot().value == "inactive"


def test_send_transitions_through_actor():
    actor = create_actor(_toggle_machine()).start()
    actor.send("TOGGLE")
    assert actor.get_snapshot().value == "active"
    actor.send("TOGGLE")
    assert actor.get_snapshot().value == "inactive"


def test_state_property_aliases_get_snapshot():
    actor = create_actor(_toggle_machine()).start()
    assert actor.state is actor.get_snapshot()


def test_stop_changes_status_and_drops_events():
    actor = create_actor(_toggle_machine()).start()
    actor.stop()
    assert actor.status == "stopped"
    # events after stop are dropped (no transition)
    actor.send("TOGGLE")
    assert actor.get_snapshot().value == "inactive"


def test_start_after_stop_is_noop():
    actor = create_actor(_toggle_machine()).start()
    actor.stop()
    actor.start()  # must not restart or re-register
    assert actor.status == "stopped"


# ---------------------------------------------------------------------------
# subscriptions
# ---------------------------------------------------------------------------


def test_subscribe_notified_on_change():
    actor = create_actor(_toggle_machine()).start()
    seen = []
    actor.subscribe(lambda state: seen.append(state.value))
    actor.send("TOGGLE")
    # immediate call on subscribe (inactive) + change (active)
    assert seen == ["inactive", "active"]


def test_unsubscribe_stops_notifications():
    actor = create_actor(_toggle_machine()).start()
    seen = []
    sub = actor.subscribe(lambda state: seen.append(state.value))
    sub.unsubscribe()
    actor.send("TOGGLE")
    assert seen == ["inactive"]  # only the initial call


# ---------------------------------------------------------------------------
# clock injection
# ---------------------------------------------------------------------------


def test_actor_uses_injected_clock_for_after():
    machine = Machine(
        {
            "id": "timed",
            "initial": "waiting",
            "states": {
                "waiting": {"after": {1000: "done"}},
                "done": {},
            },
        }
    )
    clock = SimulatedClock()
    actor = create_actor(machine, clock=clock).start()
    assert actor.get_snapshot().value == "waiting"
    clock.increment(1000)
    assert actor.get_snapshot().value == "done"


# ---------------------------------------------------------------------------
# ActorSystem
# ---------------------------------------------------------------------------


def test_actor_gets_default_id_and_system():
    actor = create_actor(_toggle_machine())
    assert actor.id is not None
    assert isinstance(actor.system, ActorSystem)


def test_explicit_id_is_used():
    actor = create_actor(_toggle_machine(), id="my-actor")
    assert actor.id == "my-actor"


def test_system_get_returns_registered_actor():
    system = ActorSystem()
    actor = create_actor(_toggle_machine(), id="root", system=system)
    assert system.get("root") is actor


def test_system_get_unknown_id_returns_none():
    system = ActorSystem()
    assert system.get("nope") is None


def test_stop_unregisters_from_system():
    system = ActorSystem()
    actor = create_actor(_toggle_machine(), id="root", system=system).start()
    assert system.get("root") is actor
    actor.stop()
    assert system.get("root") is None


def test_duplicate_id_in_same_system_raises():
    system = ActorSystem()
    create_actor(_toggle_machine(), id="dup", system=system)
    with pytest.raises(ValueError, match="already registered"):
        create_actor(_toggle_machine(), id="dup", system=system)


def test_two_actors_share_a_system():
    system = ActorSystem()
    a = create_actor(_toggle_machine(), id="a", system=system)
    b = create_actor(_toggle_machine(), id="b", system=system)
    assert system.get("a") is a
    assert system.get("b") is b
    assert a.system is b.system


def test_anonymous_ids_are_unique():
    system = ActorSystem()
    a = create_actor(_toggle_machine(), system=system)
    b = create_actor(_toggle_machine(), system=system)
    assert a.id != b.id


def test_concurrent_anonymous_actor_creation_uses_unique_ids():
    class SlowActorSystem(ActorSystem):
        def _next_id_unlocked(self) -> str:
            time.sleep(0.001)
            return super()._next_id_unlocked()

    system = SlowActorSystem()

    with ThreadPoolExecutor(max_workers=16) as pool:
        actors = list(
            pool.map(
                lambda _index: create_actor(_toggle_machine(), system=system),
                range(100),
            )
        )

    ids = {actor.id for actor in actors}

    assert len(ids) == len(actors)
    assert all(system.get(actor.id) is actor for actor in actors)

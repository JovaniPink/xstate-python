"""Tests for the synchronous Interpreter (0.3.0).

Covers the running-instance runtime that wraps the pure Machine API:
  - start / stop lifecycle and status
  - send() with run-to-completion event queueing
  - subscriptions (notify on change, unsubscribe)
  - side-effect action execution
  - context threaded through the live instance
"""

import pytest
from xstate import Machine, assign, interpret, SimulatedClock

# ---------------------------------------------------------------------------
# A small light machine with a counter context.
# ---------------------------------------------------------------------------


def make_counter():
    return Machine(
        {
            "id": "counter",
            "initial": "active",
            "context": {"count": 0},
            "states": {
                "active": {
                    "on": {
                        "INC": {
                            "actions": [
                                assign({"count": lambda ctx, _: ctx["count"] + 1})
                            ]
                        },
                        "DONE": "finished",
                    }
                },
                "finished": {"type": "final"},
            },
        }
    )


def make_light():
    return Machine(
        {
            "id": "light",
            "initial": "green",
            "states": {
                "green": {"on": {"TIMER": "yellow"}},
                "yellow": {"on": {"TIMER": "red"}},
                "red": {"on": {"TIMER": "green"}},
            },
        }
    )


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_not_started_before_start():
    service = interpret(make_light(), clock=SimulatedClock())
    assert service.status == "not_started"
    assert service.initialized is False


def test_start_sets_running_and_initial_state():
    service = interpret(make_light(), clock=SimulatedClock()).start()
    assert service.status == "running"
    assert service.initialized is True
    assert service.state.value == "green"


def test_start_is_idempotent():
    service = interpret(make_light(), clock=SimulatedClock()).start()
    service.send("TIMER")
    assert service.state.value == "yellow"
    service.start()  # no-op; must not reset to green
    assert service.state.value == "yellow"


def test_stop_sets_stopped_and_drops_events():
    service = interpret(make_light(), clock=SimulatedClock()).start()
    service.stop()
    assert service.status == "stopped"
    service.send("TIMER")  # dropped
    assert service.state.value == "green"


def test_send_before_start_is_dropped():
    service = interpret(make_light(), clock=SimulatedClock())
    service.send("TIMER")  # before start → no-op
    service.start()
    assert service.state.value == "green"


# ---------------------------------------------------------------------------
# send() basics
# ---------------------------------------------------------------------------


def test_send_advances_state():
    service = interpret(make_light(), clock=SimulatedClock()).start()
    service.send("TIMER")
    assert service.state.value == "yellow"
    service.send("TIMER")
    assert service.state.value == "red"


def test_send_returns_current_state():
    service = interpret(make_light(), clock=SimulatedClock()).start()
    state = service.send("TIMER")
    assert state.value == "yellow"


def test_send_event_dict_with_payload():
    machine = Machine(
        {
            "id": "echo",
            "initial": "idle",
            "context": {"last": None},
            "states": {
                "idle": {
                    "on": {
                        "SET": {
                            "actions": [
                                assign({"last": lambda ctx, ev: ev.data.get("value")})
                            ]
                        }
                    }
                }
            },
        }
    )
    service = interpret(machine, clock=SimulatedClock()).start()
    service.send({"type": "SET", "value": 42})
    assert service.state.context["last"] == 42


# ---------------------------------------------------------------------------
# Context updates via assign through the live instance
# ---------------------------------------------------------------------------


def test_context_accumulates_across_sends():
    service = interpret(make_counter(), clock=SimulatedClock()).start()
    service.send("INC")
    service.send("INC")
    service.send("INC")
    assert service.state.context["count"] == 3


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------


def test_subscribe_called_with_current_state_immediately():
    service = interpret(make_light(), clock=SimulatedClock()).start()
    seen = []
    service.subscribe(lambda state: seen.append(state.value))
    assert seen == ["green"]


def test_subscribe_notified_on_change():
    service = interpret(make_light(), clock=SimulatedClock()).start()
    seen = []
    service.subscribe(lambda state: seen.append(state.value))
    service.send("TIMER")
    service.send("TIMER")
    assert seen == ["green", "yellow", "red"]


def test_unsubscribe_stops_notifications():
    service = interpret(make_light(), clock=SimulatedClock()).start()
    seen = []
    sub = service.subscribe(lambda state: seen.append(state.value))
    service.send("TIMER")
    sub.unsubscribe()
    service.send("TIMER")
    assert seen == ["green", "yellow"]


# ---------------------------------------------------------------------------
# Run-to-completion: events raised by actions are processed in order
# ---------------------------------------------------------------------------


def test_action_can_send_without_reentrancy():
    """An action that calls service.send() must queue, not interleave."""
    machine = Machine(
        {
            "id": "rtc",
            "initial": "a",
            "states": {
                "a": {"on": {"GO": "b"}},
                "b": {"on": {"GO": "c"}},
                "c": {},
            },
        }
    )
    service = interpret(machine, clock=SimulatedClock()).start()
    order = []

    def watcher(state):
        order.append(state.value)
        # Re-enter send() while still processing the first event.
        if state.value == "b":
            service.send("GO")

    service.subscribe(watcher)
    service.send("GO")
    # b's nested send must be queued and processed after, reaching c.
    assert order == ["a", "b", "c"]
    assert service.state.value == "c"


# ---------------------------------------------------------------------------
# Side-effect actions execute
# ---------------------------------------------------------------------------


def test_entry_action_executes_on_transition():
    log = []
    machine = Machine(
        {
            "id": "fx",
            "initial": "a",
            "states": {
                "a": {"on": {"GO": "b"}},
                "b": {"entry": [lambda: log.append("entered-b")]},
            },
        }
    )
    service = interpret(machine, clock=SimulatedClock()).start()
    service.send("GO")
    assert "entered-b" in log

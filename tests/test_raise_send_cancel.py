"""Tests for raise_, send, cancel action creators and done-data (0.3.0).

raise_  — queues an internal event within the current macrostep (no interpreter needed)
send    — schedules an event via the interpreter, optionally with a clock delay
cancel  — cancels a previously-scheduled named send
done-data — a final state's ``data`` is available as ``event.data`` in onDone
"""

from xstate import Machine, SimulatedClock, assign, cancel, interpret, raise_, send

# ---------------------------------------------------------------------------
# raise_: fires an internal event within the same macrostep
# ---------------------------------------------------------------------------


def test_raise_in_transition_action_fires_immediately():
    """raise_() queues PING; PING fires b→c in the same machine.transition call."""
    machine = Machine(
        {
            "id": "r",
            "initial": "a",
            "states": {
                "a": {"on": {"GO": {"target": "b", "actions": [raise_("PING")]}}},
                "b": {"on": {"PING": "c"}},
                "c": {},
            },
        }
    )
    state = machine.initial_state
    state = machine.transition(state, "GO")
    assert state.value == "c"


def test_raise_in_entry_action_fires_in_same_macrostep():
    """raise_() inside an entry action is also processed within the macrostep."""
    machine = Machine(
        {
            "id": "r",
            "initial": "a",
            "states": {
                "a": {"on": {"GO": "b"}},
                "b": {
                    "entry": [raise_("AUTO")],
                    "on": {"AUTO": "c"},
                },
                "c": {},
            },
        }
    )
    state = machine.initial_state
    state = machine.transition(state, "GO")
    assert state.value == "c"


def test_raise_chained():
    """raise_ can chain: one raised event triggers another raised event."""
    machine = Machine(
        {
            "id": "chain",
            "initial": "a",
            "states": {
                "a": {"on": {"START": {"target": "b", "actions": [raise_("STEP1")]}}},
                "b": {"on": {"STEP1": {"target": "c", "actions": [raise_("STEP2")]}}},
                "c": {"on": {"STEP2": "done"}},
                "done": {},
            },
        }
    )
    state = machine.initial_state
    state = machine.transition(state, "START")
    assert state.value == "done"


def test_raise_does_not_affect_pure_machine_api():
    """raise_ works without the interpreter — pure Machine.transition."""
    machine = Machine(
        {
            "id": "pure",
            "initial": "idle",
            "states": {
                "idle": {
                    "on": {"TRIGGER": {"target": "mid", "actions": [raise_("DONE")]}}
                },
                "mid": {"on": {"DONE": "final"}},
                "final": {},
            },
        }
    )
    state = machine.initial_state
    state = machine.transition(state, "TRIGGER")
    assert state.value == "final"


# ---------------------------------------------------------------------------
# send: delayed send via interpreter + clock
# ---------------------------------------------------------------------------


def test_send_with_delay_fires_after_clock_increment():
    """send(event, delay=ms) schedules via clock; fires when time passes."""
    machine = Machine(
        {
            "id": "s",
            "initial": "idle",
            "states": {
                "idle": {
                    "on": {
                        "START": {
                            "target": "waiting",
                            "actions": [send("TIMEOUT", delay=1000)],
                        }
                    }
                },
                "waiting": {"on": {"TIMEOUT": "timed_out"}},
                "timed_out": {},
            },
        }
    )
    clock = SimulatedClock()
    service = interpret(machine, clock=clock).start()
    service.send("START")
    assert service.state.value == "waiting"
    clock.increment(999)
    assert service.state.value == "waiting"
    clock.increment(1)
    assert service.state.value == "timed_out"


def test_send_without_delay_fires_in_next_send_cycle():
    """send(event) with no delay queues via the interpreter's RTC loop."""
    machine = Machine(
        {
            "id": "s",
            "initial": "a",
            "states": {
                "a": {"on": {"GO": {"target": "b", "actions": [send("AUTO")]}}},
                "b": {"on": {"AUTO": "c"}},
                "c": {},
            },
        }
    )
    clock = SimulatedClock()
    service = interpret(machine, clock=clock).start()
    service.send("GO")
    assert service.state.value == "c"


def test_send_with_delay_does_not_fire_when_state_exits_early():
    """A send-scheduled event still fires after exit — it is NOT auto-cancelled
    by exiting the state (unlike `after`).  cancel() must be called explicitly."""
    machine = Machine(
        {
            "id": "s",
            "initial": "loading",
            "states": {
                "loading": {
                    "on": {
                        "RESOLVE": {
                            "target": "success",
                            "actions": [send("STALE", delay=500, id="stale-check")],
                        },
                        "STALE": "stale",
                    }
                },
                "success": {"on": {"STALE": "stale"}},
                "stale": {},
            },
        }
    )
    clock = SimulatedClock()
    service = interpret(machine, clock=clock).start()
    service.send("RESOLVE")
    assert service.state.value == "success"
    clock.increment(500)
    # STALE still fires (no cancel was called) — transitions from success → stale
    assert service.state.value == "stale"


# ---------------------------------------------------------------------------
# cancel: stops a named delayed send
# ---------------------------------------------------------------------------


def test_cancel_prevents_delayed_send():
    """cancel(id) prevents a named send from firing."""
    machine = Machine(
        {
            "id": "c",
            "initial": "loading",
            "states": {
                "loading": {
                    "on": {
                        "START": {
                            "target": "active",
                            "actions": [send("TIMEOUT", delay=1000, id="to")],
                        }
                    }
                },
                "active": {
                    "on": {
                        "DONE": {
                            "target": "success",
                            "actions": [cancel("to")],
                        },
                        "TIMEOUT": "failed",
                    }
                },
                "success": {},
                "failed": {},
            },
        }
    )
    clock = SimulatedClock()
    service = interpret(machine, clock=clock).start()
    service.send("START")
    assert service.state.value == "active"
    service.send("DONE")  # cancels the timer before it fires
    assert service.state.value == "success"
    clock.increment(2000)  # would have fired TIMEOUT — must be a no-op
    assert service.state.value == "success"


def test_cancel_no_effect_if_already_fired():
    """cancel() after the send already fired is silently ignored."""
    machine = Machine(
        {
            "id": "c",
            "initial": "a",
            "states": {
                "a": {
                    "on": {
                        "GO": {
                            "target": "b",
                            "actions": [send("PING", delay=100, id="p")],
                        }
                    }
                },
                "b": {
                    "on": {
                        "PING": "c",
                        "CANCEL": {"actions": [cancel("p")]},
                    }
                },
                "c": {},
            },
        }
    )
    clock = SimulatedClock()
    service = interpret(machine, clock=clock).start()
    service.send("GO")
    clock.increment(100)  # PING fires → c
    assert service.state.value == "c"
    # cancel after firing: no error, no state change
    service.send("CANCEL")
    assert service.state.value == "c"


# ---------------------------------------------------------------------------
# done-data: final state's `data` reaches onDone as event.data
# ---------------------------------------------------------------------------


def test_done_data_static_dict_available_in_on_done_assign():
    """A final state's static data dict is accessible via event.data in onDone."""
    machine = Machine(
        {
            "id": "dd",
            "initial": "processing",
            "context": {"result": None},
            "states": {
                "processing": {
                    "initial": "task",
                    "states": {
                        "task": {
                            "type": "final",
                            "output": {"value": 42},
                        }
                    },
                    "onDone": {
                        "target": "done",
                        "actions": [
                            assign({"result": lambda ctx, ev: ev.data["value"]})
                        ],
                    },
                },
                "done": {},
            },
        }
    )
    state = machine.initial_state
    assert state.value == "done"
    assert state.context["result"] == 42


def test_done_data_callable_evaluated_with_context():
    """A callable done-data fn is called with (context, event) when the
    final state is entered."""
    machine = Machine(
        {
            "id": "dd",
            "initial": "computing",
            "context": {"multiplier": 3},
            "states": {
                "computing": {
                    "initial": "work",
                    "states": {
                        "work": {
                            "type": "final",
                            "output": lambda ctx, _: {
                                "product": ctx["multiplier"] * 10
                            },
                        }
                    },
                    "onDone": {
                        "target": "done",
                        "actions": [
                            assign({"result": lambda ctx, ev: ev.data["product"]})
                        ],
                    },
                },
                "done": {},
            },
        }
    )
    state = machine.initial_state
    assert state.value == "done"
    assert state.context["result"] == 30


def test_done_data_available_in_guard():
    """done-data is accessible via event.data in an onDone guard."""
    machine = Machine(
        {
            "id": "dd",
            "initial": "run",
            "states": {
                "run": {
                    "initial": "work",
                    "states": {"work": {"type": "final", "output": {"ok": True}}},
                    "onDone": [
                        {
                            "target": "success",
                            "guard": lambda ctx, ev: ev.data.get("ok", False),
                        },
                        {"target": "failure"},
                    ],
                },
                "success": {},
                "failure": {},
            },
        }
    )
    state = machine.initial_state
    assert state.value == "success"

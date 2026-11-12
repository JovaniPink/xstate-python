"""Tests for delayed (`after`) transitions (0.3.0).

Delayed transitions are scheduled by the interpreter when their state is
entered and cancelled when it is exited.  A SimulatedClock makes time
deterministic: nothing fires until the test calls ``clock.increment(ms)``.
"""

import asyncio
import json

import pytest

from xstate import (
    InvalidConfigError,
    Machine,
    SimulatedClock,
    UnregisteredImplementationError,
    interpret,
    interpret_async,
    send,
)

# ---------------------------------------------------------------------------
# Classic auto-advancing traffic light using `after`.
# ---------------------------------------------------------------------------


def make_timed_light():
    return Machine(
        {
            "id": "light",
            "initial": "green",
            "states": {
                "green": {"after": {1000: "yellow"}},
                "yellow": {"after": {500: "red"}},
                "red": {"after": {2000: "green"}},
            },
        }
    )


def test_after_does_not_fire_before_delay():
    clock = SimulatedClock()
    service = interpret(make_timed_light(), clock=clock).start()
    assert service.state.value == "green"
    clock.increment(999)
    assert service.state.value == "green"


def test_after_fires_at_delay():
    clock = SimulatedClock()
    service = interpret(make_timed_light(), clock=clock).start()
    clock.increment(1000)
    assert service.state.value == "yellow"


def test_after_chains_through_states():
    clock = SimulatedClock()
    service = interpret(make_timed_light(), clock=clock).start()
    clock.increment(1000)  # green → yellow
    assert service.state.value == "yellow"
    clock.increment(500)  # yellow → red
    assert service.state.value == "red"
    clock.increment(2000)  # red → green
    assert service.state.value == "green"


def test_after_single_large_increment_cascades():
    """One big time jump fires successive due timers in order."""
    clock = SimulatedClock()
    service = interpret(make_timed_light(), clock=clock).start()
    clock.increment(1500)  # crosses green(1000) then yellow(500)
    assert service.state.value == "red"


# ---------------------------------------------------------------------------
# A manual event cancels a pending `after` timer.
# ---------------------------------------------------------------------------


def make_cancellable():
    return Machine(
        {
            "id": "cancel",
            "initial": "loading",
            "states": {
                "loading": {
                    "after": {1000: "timeout"},
                    "on": {"RESOLVE": "success"},
                },
                "success": {},
                "timeout": {},
            },
        }
    )


def test_event_before_delay_cancels_timer():
    clock = SimulatedClock()
    service = interpret(make_cancellable(), clock=clock).start()
    clock.increment(500)
    service.send("RESOLVE")  # leaves `loading`, cancelling its after-timer
    assert service.state.value == "success"
    clock.increment(1000)  # the cancelled timer must NOT fire
    assert service.state.value == "success"


def test_timer_fires_if_no_event():
    clock = SimulatedClock()
    service = interpret(make_cancellable(), clock=clock).start()
    clock.increment(1000)
    assert service.state.value == "timeout"


# ---------------------------------------------------------------------------
# Guarded `after` transition (array form).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ready,expected", [(False, "stay"), (True, "go")])
def test_after_with_guard(ready, expected):
    """First guard wins when true; falls through to second target when false."""
    machine = Machine(
        {
            "id": "guarded",
            "initial": "waiting",
            "context": {"ready": ready},
            "states": {
                "waiting": {
                    "after": {
                        1000: [
                            {"target": "go", "guard": lambda ctx, _: ctx["ready"]},
                            {"target": "stay"},
                        ]
                    }
                },
                "go": {},
                "stay": {},
            },
        }
    )
    clock = SimulatedClock()
    service = interpret(machine, clock=clock).start()
    clock.increment(1000)
    assert service.state.value == expected


# ---------------------------------------------------------------------------
# Named delay reference resolved from Machine(delays=...).
# ---------------------------------------------------------------------------


def test_named_delay_reference():
    machine = Machine(
        {
            "id": "named",
            "initial": "a",
            "states": {
                "a": {"after": {"SHORT": "b"}},
                "b": {},
            },
        },
        delays={"SHORT": 750},
    )
    clock = SimulatedClock()
    service = interpret(machine, clock=clock).start()
    clock.increment(749)
    assert service.state.value == "a"
    clock.increment(1)
    assert service.state.value == "b"


def test_named_delay_callable_uses_context():
    machine = Machine(
        {
            "id": "named",
            "initial": "a",
            "context": {"wait": 300},
            "states": {
                "a": {"after": {"DYNAMIC": "b"}},
                "b": {},
            },
        },
        delays={"DYNAMIC": lambda ctx, _: ctx["wait"]},
    )
    clock = SimulatedClock()
    service = interpret(machine, clock=clock).start()
    clock.increment(300)
    assert service.state.value == "b"


def test_missing_named_delay_raises():
    machine = Machine(
        {
            "id": "named",
            "initial": "a",
            "states": {"a": {"after": {"NOPE": "b"}}, "b": {}},
        }
    )
    clock = SimulatedClock()
    with pytest.raises(UnregisteredImplementationError, match="Delay 'NOPE'"):
        interpret(machine, clock=clock).start()


# ---------------------------------------------------------------------------
# `after` inside a compound child; parent transition cancels child timer.
# ---------------------------------------------------------------------------


def test_after_in_nested_state_cancelled_by_parent_transition():
    machine = Machine(
        {
            "id": "nested",
            "initial": "outer",
            "states": {
                "outer": {
                    "initial": "inner1",
                    "on": {"ESCAPE": "done"},
                    "states": {
                        "inner1": {"after": {1000: "inner2"}},
                        "inner2": {},
                    },
                },
                "done": {},
            },
        }
    )
    clock = SimulatedClock()
    service = interpret(machine, clock=clock).start()
    assert service.state.value == {"outer": "inner1"}
    service.send("ESCAPE")  # exits outer (and inner1), cancelling timer
    assert service.state.value == "done"
    clock.increment(1000)  # must not resurrect inner2
    assert service.state.value == "done"


def test_after_in_nested_state_fires():
    machine = Machine(
        {
            "id": "nested",
            "initial": "outer",
            "states": {
                "outer": {
                    "initial": "inner1",
                    "states": {
                        "inner1": {"after": {1000: "inner2"}},
                        "inner2": {},
                    },
                },
            },
        }
    )
    clock = SimulatedClock()
    service = interpret(machine, clock=clock).start()
    clock.increment(1000)
    assert service.state.value == {"outer": "inner2"}


def json_after_config(delay):
    """Exercise the serialized boundary, whose object keys are always strings."""
    return json.loads(
        json.dumps(
            {
                "id": "jsonDelay",
                "initial": "waiting",
                "states": {
                    "waiting": {"after": {delay: "elapsed"}},
                    "elapsed": {},
                },
            }
        )
    )


def test_literal_json_after_fires_at_1000_milliseconds():
    config = json.loads(
        """{
            "id": "jsonDelay",
            "initial": "waiting",
            "states": {
                "waiting": {"after": {"1000": "elapsed"}},
                "elapsed": {}
            }
        }"""
    )
    clock = SimulatedClock()
    service = interpret(Machine(config), clock=clock).start()
    clock.increment(999)
    assert service.state.value == "waiting"
    clock.increment(1)
    assert service.state.value == "elapsed"
    service.stop()


@pytest.mark.parametrize(
    "delay,milliseconds",
    [("0", 0), ("0.5", 0.5), ("1e3", 1000), ("2.5E+2", 250), ("1e-2", 0.01)],
)
def test_json_after_supports_nonnegative_decimal_and_exponent_keys(delay, milliseconds):
    clock = SimulatedClock()
    service = interpret(Machine(json_after_config(delay)), clock=clock).start()
    assert service.state.value == "waiting"
    if milliseconds:
        clock.increment(milliseconds / 2)
        assert service.state.value == "waiting"
        clock.increment(milliseconds / 2)
    else:
        clock.increment(0)
    assert service.state.value == "elapsed"
    service.stop()


def test_numeric_after_key_takes_precedence_over_named_registry():
    def must_not_resolve(*args):
        pytest.fail("A numeric after key must not invoke a named delay")

    machine = Machine(json_after_config("1000"), delays={"1000": must_not_resolve})
    clock = SimulatedClock()
    service = interpret(machine, clock=clock).start()
    clock.increment(999)
    assert service.state.value == "waiting"
    clock.increment(1)
    assert service.state.value == "elapsed"
    service.stop()


@pytest.mark.parametrize("delay", ["1e309", "9.9e9999"])
def test_overflowing_numeric_after_key_is_rejected_at_construction(delay):
    with pytest.raises(InvalidConfigError, match=r"states.waiting.after.*finite"):
        Machine(json_after_config(delay))


@pytest.mark.parametrize(
    "name", ["001", "+1", " 1 ", "0x10", "Infinity", "-1", "1_000", "NaN", ""]
)
def test_strings_outside_numeric_after_grammar_remain_named_delays(name):
    clock = SimulatedClock()
    service = interpret(
        Machine(json_after_config(name), delays={name: 7}), clock=clock
    ).start()
    clock.increment(6)
    assert service.state.value == "waiting"
    clock.increment(1)
    assert service.state.value == "elapsed"
    service.stop()


def test_numeric_string_send_delay_still_uses_named_registry():
    machine = Machine(
        {
            "id": "namedSendDelay",
            "initial": "waiting",
            "states": {
                "waiting": {
                    "entry": send("EXPIRE", delay="1000"),
                    "on": {"EXPIRE": "elapsed"},
                },
                "elapsed": {},
            },
        },
        delays={"1000": 2000},
    )
    clock = SimulatedClock()
    service = interpret(machine, clock=clock).start()
    clock.increment(1000)
    assert service.state.value == "waiting"
    clock.increment(1000)
    assert service.state.value == "elapsed"
    service.stop()


def test_leaving_state_cancels_literal_json_after_timer():
    config = json_after_config("1000")
    config["states"]["waiting"]["on"] = {"CANCEL": "cancelled"}
    config["states"]["cancelled"] = {}
    clock = SimulatedClock()
    service = interpret(Machine(config), clock=clock).start()
    clock.increment(999)
    service.send("CANCEL")
    clock.increment(1)
    assert service.state.value == "cancelled"
    service.stop()


async def test_async_runtime_schedules_literal_json_after():
    service = interpret_async(Machine(json_after_config("1")))
    elapsed = asyncio.Event()
    service.subscribe(lambda state: elapsed.set() if state.value == "elapsed" else None)
    try:
        await service.start()
        await asyncio.wait_for(elapsed.wait(), timeout=1)
        assert service.state.value == "elapsed"
    finally:
        await service.stop()

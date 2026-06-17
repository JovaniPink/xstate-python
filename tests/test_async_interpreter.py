"""Tests for the asyncio-native AsyncInterpreter (0.5.0).

The pure transition layer is shared with the synchronous interpreter; these
tests focus on the async runtime: ``await`` lifecycle, run-to-completion under
cooperative scheduling, awaitable action callables, and event-loop-scheduled
delayed transitions.
"""

import asyncio

from xstate import Machine, interpret_async
from xstate.async_interpreter import AsyncInterpreter

# ---------------------------------------------------------------------------
# Lifecycle + basic transitions
# ---------------------------------------------------------------------------


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


async def test_start_returns_self_and_initial_state():
    service = await interpret_async(_toggle_machine()).start()
    assert isinstance(service, AsyncInterpreter)
    assert service.status == "running"
    assert service.state.value == "inactive"


async def test_send_transitions():
    service = await interpret_async(_toggle_machine()).start()
    await service.send("TOGGLE")
    assert service.state.value == "active"
    await service.send("TOGGLE")
    assert service.state.value == "inactive"


async def test_send_returns_resulting_state():
    service = await interpret_async(_toggle_machine()).start()
    state = await service.send("TOGGLE")
    assert state.value == "active"


async def test_start_is_idempotent():
    service = await interpret_async(_toggle_machine()).start()
    await service.start()  # no-op, stays running
    assert service.status == "running"
    assert service.state.value == "inactive"


async def test_events_dropped_before_start_and_after_stop():
    service = interpret_async(_toggle_machine())
    # before start
    await service.send("TOGGLE")
    assert service.state.value == "inactive"
    await service.start()
    await service.send("TOGGLE")
    assert service.state.value == "active"
    await service.stop()
    assert service.status == "stopped"
    # after stop
    await service.send("TOGGLE")
    assert service.state.value == "active"


# ---------------------------------------------------------------------------
# Awaitable action callables
# ---------------------------------------------------------------------------


async def test_async_action_callable_is_awaited():
    log: list[str] = []

    async def record():
        await asyncio.sleep(0)
        log.append("ran")

    machine = Machine(
        {
            "id": "a",
            "initial": "idle",
            "states": {
                "idle": {"on": {"GO": {"target": "active", "actions": [record]}}},
                "active": {},
            },
        }
    )
    service = await interpret_async(machine).start()
    await service.send("GO")
    assert service.state.value == "active"
    assert log == ["ran"]


async def test_sync_action_callable_still_runs():
    log: list[str] = []
    machine = Machine(
        {
            "id": "a",
            "initial": "idle",
            "states": {
                "idle": {
                    "on": {
                        "GO": {"target": "active", "actions": [lambda: log.append("s")]}
                    }
                },
                "active": {},
            },
        }
    )
    service = await interpret_async(machine).start()
    await service.send("GO")
    assert log == ["s"]


async def test_entry_async_action_runs_on_start():
    log: list[str] = []

    async def on_entry():
        log.append("entered")

    machine = Machine(
        {
            "id": "a",
            "initial": "idle",
            "states": {"idle": {"entry": [on_entry]}},
        }
    )
    await interpret_async(machine).start()
    assert log == ["entered"]


# ---------------------------------------------------------------------------
# Run-to-completion
# ---------------------------------------------------------------------------


async def test_raise_processed_in_same_macrostep():
    """raise_ queues an internal event handled within machine.transition."""
    from xstate import raise_

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
    service = await interpret_async(machine).start()
    await service.send("GO")
    assert service.state.value == "c"


async def test_send_action_without_delay_drains_in_rtc():
    machine = Machine(
        {
            "id": "s",
            "initial": "a",
            "states": {
                "a": {"on": {"GO": {"target": "b", "actions": [_send("AUTO")]}}},
                "b": {"on": {"AUTO": "c"}},
                "c": {},
            },
        }
    )
    service = await interpret_async(machine).start()
    await service.send("GO")
    assert service.state.value == "c"


# ---------------------------------------------------------------------------
# Delayed transitions (after) scheduled on the event loop
# ---------------------------------------------------------------------------


async def test_after_fires_following_real_delay():
    machine = Machine(
        {
            "id": "t",
            "initial": "loading",
            "states": {
                "loading": {"after": {20: "loaded"}},
                "loaded": {},
            },
        }
    )
    service = await interpret_async(machine).start()
    assert service.state.value == "loading"
    await asyncio.sleep(0.05)
    assert service.state.value == "loaded"


async def test_after_cancelled_when_state_exits_before_firing():
    machine = Machine(
        {
            "id": "t",
            "initial": "loading",
            "states": {
                "loading": {"after": {50: "timeout"}, "on": {"RESOLVE": "done"}},
                "timeout": {},
                "done": {},
            },
        }
    )
    service = await interpret_async(machine).start()
    await service.send("RESOLVE")
    assert service.state.value == "done"
    await asyncio.sleep(0.08)
    # The timer was cancelled on exit; it must not knock us out of `done`.
    assert service.state.value == "done"


async def test_stop_cancels_pending_after():
    machine = Machine(
        {
            "id": "t",
            "initial": "waiting",
            "states": {"waiting": {"after": {30: "fired"}}, "fired": {}},
        }
    )
    service = await interpret_async(machine).start()
    await service.stop()
    await asyncio.sleep(0.05)
    # Stopped service ignores the fired timer.
    assert service.state.value == "waiting"
    assert service.status == "stopped"


async def test_named_delay_resolved_from_machine_delays():
    machine = Machine(
        {
            "id": "t",
            "initial": "a",
            "states": {"a": {"after": {"SHORT": "b"}}, "b": {}},
        },
        delays={"SHORT": 20},
    )
    service = await interpret_async(machine).start()
    await asyncio.sleep(0.05)
    assert service.state.value == "b"


# ---------------------------------------------------------------------------
# Delayed send + cancel
# ---------------------------------------------------------------------------


async def test_delayed_send_fires_after_delay():
    machine = Machine(
        {
            "id": "s",
            "initial": "idle",
            "states": {
                "idle": {
                    "on": {
                        "START": {
                            "target": "waiting",
                            "actions": [_send("TIMEOUT", delay=20)],
                        }
                    }
                },
                "waiting": {"on": {"TIMEOUT": "done"}},
                "done": {},
            },
        }
    )
    service = await interpret_async(machine).start()
    await service.send("START")
    assert service.state.value == "waiting"
    await asyncio.sleep(0.05)
    assert service.state.value == "done"


async def test_cancel_prevents_delayed_send():
    machine = Machine(
        {
            "id": "c",
            "initial": "loading",
            "states": {
                "loading": {
                    "on": {
                        "START": {
                            "target": "active",
                            "actions": [_send("TIMEOUT", delay=30, id="to")],
                        }
                    }
                },
                "active": {
                    "on": {
                        "DONE": {"target": "success", "actions": [_cancel("to")]},
                        "TIMEOUT": "failed",
                    }
                },
                "success": {},
                "failed": {},
            },
        }
    )
    service = await interpret_async(machine).start()
    await service.send("START")
    await service.send("DONE")
    assert service.state.value == "success"
    await asyncio.sleep(0.05)
    assert service.state.value == "success"


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------


async def test_subscribe_notified_on_change_and_unsubscribe():
    seen: list[str] = []
    service = await interpret_async(_toggle_machine()).start()
    sub = service.subscribe(lambda state: seen.append(state.value))
    # immediate call with current state on subscribe
    assert seen == ["inactive"]
    await service.send("TOGGLE")
    assert seen == ["inactive", "active"]
    sub.unsubscribe()
    await service.send("TOGGLE")
    assert seen == ["inactive", "active"]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _send(event, *, delay=None, id=None):
    from xstate import send

    return send(event, delay=delay, id=id)


def _cancel(send_id):
    from xstate import cancel

    return cancel(send_id)

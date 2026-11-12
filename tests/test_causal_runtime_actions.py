"""Runtime-owned sends resolve named delays from their causal arguments."""

import asyncio

import pytest

from xstate import (
    Machine,
    SimulatedClock,
    assign,
    create_actor,
    get_microsteps,
    interpret,
    interpret_async,
    raise_,
    send,
    send_parent,
    send_to,
)
from xstate.actor import ActorSystem


def delayed_machine(delay):
    record = assign(
        {"received": lambda args: [*args.context["received"], args.event.name]}
    )
    return Machine(
        {
            "id": "causal-send",
            "initial": "idle",
            "context": {"delay_ms": 20, "received": []},
            "states": {
                "idle": {
                    "on": {
                        "GO": {
                            "target": "waiting",
                            "actions": [
                                send("FIRST", delay="dynamic"),
                                assign({"delay_ms": 200}),
                                raise_("INNER"),
                            ],
                        }
                    }
                },
                "waiting": {
                    "on": {
                        "INNER": {
                            "actions": [
                                send("SECOND", delay="dynamic"),
                                assign({"delay_ms": 500}),
                            ]
                        },
                        "FIRST": {"actions": record},
                        "SECOND": {"actions": record},
                    }
                },
            },
        },
        delays={"dynamic": delay},
    )


@pytest.mark.parametrize("traced", [False, True])
def test_sync_send_delay_uses_action_position_and_internal_event(traced):
    seen = []
    traces = []

    def delay(args):
        seen.append((args.context["delay_ms"], args.event.name))
        return args.context["delay_ms"]

    clock = SimulatedClock()
    service = interpret(
        delayed_machine(delay),
        clock=clock,
        inspect=traces.append if traced else None,
    ).start()
    try:
        service.send("GO")
        assert seen == [(20, "GO"), (200, "INNER")]
        assert service.state.context == {"delay_ms": 500, "received": []}
        assert service.state.event.name == "GO"
        clock.increment(19)
        assert service.state.context["received"] == []
        clock.increment(1)
        assert service.state.context["received"] == ["FIRST"]
        clock.increment(179)
        assert service.state.context["received"] == ["FIRST"]
        clock.increment(1)
        assert service.state.context["received"] == ["FIRST", "SECOND"]
    finally:
        service.stop()


@pytest.mark.parametrize("traced", [False, True])
async def test_async_send_delay_uses_action_position_and_internal_event(traced):
    seen = []
    traces = []
    received_both = asyncio.Event()

    def delay(args):
        seen.append((args.context["delay_ms"], args.event.name))
        # Argument binding is deterministic; actual deadline behavior is covered
        # by the simulated-clock test above rather than wall-clock sleeps.
        return 0

    service = await interpret_async(
        delayed_machine(delay), inspect=traces.append if traced else None
    ).start()
    service.subscribe(
        lambda state: (
            received_both.set() if len(state.context["received"]) == 2 else None
        )
    )
    try:
        await service.send("GO")
        assert seen == [(20, "GO"), (200, "INNER")]
        assert service.state.context["delay_ms"] == 500
        await asyncio.wait_for(received_both.wait(), timeout=1)
        assert service.state.context["received"] == ["FIRST", "SECOND"]
    finally:
        await service.stop()


@pytest.mark.parametrize("route", ["parent", "named-actor"])
def test_external_send_delay_uses_context_before_later_assignment(route):
    seen = []

    def delay(args):
        seen.append((args.context["delay_ms"], args.event.name))
        return args.context["delay_ms"]

    recipient = Machine(
        {
            "id": "receiver",
            "initial": "idle",
            "context": {"count": 0},
            "states": {
                "idle": {
                    "on": {
                        "PING": {
                            "actions": assign(
                                {"count": lambda args: args.context["count"] + 1}
                            )
                        }
                    }
                }
            },
        }
    )
    message = (
        send_parent("PING", delay="dynamic")
        if route == "parent"
        else send_to("receiver", "PING", delay="dynamic")
    )
    emitter = Machine(
        {
            "id": "emitter",
            "initial": "idle",
            "context": {"delay_ms": 20},
            "states": {
                "idle": {
                    "on": {
                        "GO": {
                            "target": "waiting",
                            "actions": [message, assign({"delay_ms": 200})],
                        }
                    }
                },
                "waiting": {},
            },
        },
        delays={"dynamic": delay},
    )
    clock = SimulatedClock()
    system = ActorSystem()
    receiver = create_actor(recipient, id="receiver", system=system).start()
    sender = (
        receiver.spawn(emitter, id="emitter", clock=clock)
        if route == "parent"
        else create_actor(emitter, id="emitter", system=system, clock=clock)
    ).start()
    try:
        sender.send("GO")
        assert seen == [(20, "GO")]
        assert sender.state.context == {"delay_ms": 200}
        clock.increment(19)
        assert receiver.state.context["count"] == 0
        clock.increment(1)
        assert receiver.state.context["count"] == 1
    finally:
        sender.stop()
        receiver.stop()


def test_queries_do_not_resolve_runtime_owned_delays():
    def unexpected_delay(args):
        raise AssertionError("Delay evaluation belongs to runtime execution")

    machine = delayed_machine(unexpected_delay)
    initial = machine.initial_state
    assert initial.can("GO")
    assert machine.transition(initial, "GO").context["delay_ms"] == 500
    assert (
        get_microsteps(machine, initial, "GO")[-1].snapshot.context["delay_ms"] == 500
    )


def failing_delay_machine(seen):
    def delay(args):
        seen.append((args.context["delay_ms"], args.event.name))
        raise ValueError("delay implementation failed")

    return delayed_machine(delay)


def test_sync_delay_failure_keeps_final_state_committed():
    seen = []
    service = interpret(failing_delay_machine(seen), clock=SimulatedClock()).start()
    try:
        with pytest.raises(ValueError, match="delay implementation failed"):
            service.send("GO")
        assert seen == [(20, "GO")]
        assert service.state.value == "waiting"
        assert service.state.context == {"delay_ms": 500, "received": []}
        assert service.state.event.name == "GO"
    finally:
        service.stop()


async def test_async_delay_failure_keeps_final_state_committed():
    seen = []
    service = await interpret_async(failing_delay_machine(seen)).start()
    try:
        with pytest.raises(ValueError, match="delay implementation failed"):
            await service.send("GO")
        assert seen == [(20, "GO")]
        assert service.state.value == "waiting"
        assert service.state.context == {"delay_ms": 500, "received": []}
        assert service.state.event.name == "GO"
    finally:
        await service.stop()

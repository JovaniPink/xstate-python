"""Initialization shares the event queue's run-to-completion boundary."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event as ThreadEvent

import pytest

from xstate import (
    Machine,
    SimulatedClock,
    create_actor,
    interpret,
    interpret_async,
    send,
)


def startup_machine(first, log, *, after=None):
    return Machine(
        {
            "id": "startup",
            "initial": "a",
            "states": {
                "a": {
                    "entry": [first, lambda: log.append("initial:second")],
                    "on": {"GO": {"target": "b", "actions": "move"}},
                    **({"after": after} if after else {}),
                },
                "b": {"on": {"NEXT": {"actions": "next"}}},
            },
        },
        actions={
            "move": lambda: log.append("transition:GO"),
            "next": lambda: log.append("transition:NEXT"),
        },
    )


@pytest.mark.parametrize("source", ["action", "builtin", "inspect", "subscriber"])
def test_sync_startup_sends_wait_for_actions_and_initial_notification(source):
    log = []
    notifications = []
    returned = []

    def enqueue():
        returned.append(service.send("GO").value)
        service.send("NEXT")

    def first():
        log.append("initial:first")
        if source == "action":
            enqueue()

    machine = startup_machine(send("GO") if source == "builtin" else first, log)

    def inspect(trace):
        if source == "inspect" and trace.previous_snapshot is None:
            enqueue()

    service = interpret(machine, inspect=inspect)

    def observe(state):
        notifications.append(state.value)
        log.append(f"notify:{state.value}")
        if source == "subscriber" and state.value == "a":
            enqueue()

    service.subscribe(observe)
    try:
        service.start()
        assert notifications == (["a", "b"] if source == "builtin" else ["a", "b", "b"])
        assert (
            log.index("initial:second")
            < log.index("notify:a")
            < log.index("transition:GO")
        )
        if source != "builtin":
            assert returned == ["a"]
            assert log[-2:] == ["transition:NEXT", "notify:b"]
    finally:
        service.stop()


@pytest.mark.parametrize("source", ["action", "builtin", "inspect", "subscriber"])
async def test_async_startup_sends_wait_for_actions_and_initial_notification(source):
    log = []
    notifications = []
    returned = []
    tasks = []

    async def enqueue():
        returned.append((await service.send("GO")).value)
        await service.send("NEXT")

    async def first():
        log.append("initial:first")
        if source == "action":
            await enqueue()
        elif source == "inspect":
            # Let the task created by the inspector enqueue while startup owns
            # processing, without waiting for that task inside the action.
            await asyncio.sleep(0)

    def inspect(trace):
        if source == "inspect" and trace.previous_snapshot is None:
            tasks.append(asyncio.create_task(enqueue()))

    machine = startup_machine(send("GO") if source == "builtin" else first, log)
    service = interpret_async(machine, inspect=inspect)

    def observe(state):
        notifications.append(state.value)
        log.append(f"notify:{state.value}")
        if source == "subscriber" and state.value == "a":
            tasks.append(asyncio.create_task(enqueue()))

    service.subscribe(observe)
    try:
        await service.start()
        await asyncio.gather(*tasks)
        assert notifications == (["a", "b"] if source == "builtin" else ["a", "b", "b"])
        assert (
            log.index("initial:second")
            < log.index("notify:a")
            < log.index("transition:GO")
        )
        if source == "action":
            assert returned == ["a"]
        elif source in {"inspect", "subscriber"}:
            assert returned == ["b"]
        if source != "builtin":
            assert log[-2:] == ["transition:NEXT", "notify:b"]
    finally:
        await service.stop()


def test_sync_timer_send_during_blocked_initial_action_is_queued():
    log = []
    entered, release = ThreadEvent(), ThreadEvent()
    clock = SimulatedClock()

    def first():
        log.append("initial:first")
        entered.set()
        assert release.wait(5)

    machine = startup_machine(first, log, after={1: {"target": "b", "actions": "move"}})
    service = interpret(machine, clock=clock)
    service.subscribe(lambda state: log.append(f"notify:{state.value}"))
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            startup = pool.submit(service.start)
            assert entered.wait(5)
            try:
                clock.increment(1)
                assert service.state.value == "a"
                assert log == ["initial:first"]
            finally:
                release.set()
            startup.result(timeout=5)
        assert log == [
            "initial:first",
            "initial:second",
            "notify:a",
            "transition:GO",
            "notify:b",
        ]
    finally:
        service.stop()


async def test_async_concurrent_sends_wait_and_keep_fifo_during_startup():
    log = []
    entered, release = asyncio.Event(), asyncio.Event()

    async def first():
        log.append("initial:first")
        entered.set()
        await release.wait()

    service = interpret_async(startup_machine(first, log))
    service.subscribe(lambda state: log.append(f"notify:{state.value}"))
    startup = asyncio.create_task(service.start())
    try:
        await asyncio.wait_for(entered.wait(), 5)
        go = asyncio.create_task(service.send("GO"))
        next_event = asyncio.create_task(service.send("NEXT"))
        await asyncio.sleep(0)
        assert not go.done() and not next_event.done()
        assert log == ["initial:first"]
        release.set()
        await asyncio.wait_for(asyncio.gather(startup, go, next_event), 5)
        assert (go.result().value, next_event.result().value) == ("b", "b")
        assert log == [
            "initial:first",
            "initial:second",
            "notify:a",
            "transition:GO",
            "notify:b",
            "transition:NEXT",
            "notify:b",
        ]
    finally:
        release.set()
        await service.stop()


def test_sync_failed_startup_discards_queue_and_releases_processing():
    log = []
    error = ValueError("initial action failed")

    def first():
        service.send("GO")
        raise error

    service = interpret(startup_machine(first, log))
    try:
        with pytest.raises(ValueError) as caught:
            service.start()
        assert caught.value is error
        assert service.status == "running"
        assert service.state.value == "a"
        assert log == []
        assert service.send("GO").value == "b"
        assert log == ["transition:GO"]
    finally:
        service.stop()


@pytest.mark.parametrize("cancel", [False, True])
async def test_async_failed_startup_settles_waiters_and_releases_processing(cancel):
    log = []
    entered, release = asyncio.Event(), asyncio.Event()
    error = ValueError("initial action failed")

    async def first():
        entered.set()
        await release.wait()
        raise error

    service = interpret_async(startup_machine(first, log))
    startup = asyncio.create_task(service.start())
    try:
        await asyncio.wait_for(entered.wait(), 5)
        waiting = asyncio.create_task(service.send("GO"))
        await asyncio.sleep(0)
        assert not waiting.done()
        if cancel:
            startup.cancel()
        else:
            release.set()
        results = await asyncio.wait_for(
            asyncio.gather(startup, waiting, return_exceptions=True), 5
        )
        if cancel:
            assert all(isinstance(result, asyncio.CancelledError) for result in results)
        else:
            assert results == [error, error]
        assert service.status == "running"
        assert service.state.value == "a"
        assert log == []
        assert (await service.send("GO")).value == "b"
        assert log == ["transition:GO"]
    finally:
        release.set()
        await service.stop()


def test_sync_stop_from_initial_action_skips_remaining_actions_and_notifications():
    log = []

    def first():
        service.send("GO")
        service.stop()

    service = interpret(startup_machine(first, log))
    service.subscribe(lambda state: log.append(f"notify:{state.value}"))
    service.start()
    assert service.status == "stopped"
    assert service.state.value == "a"
    assert log == []


async def test_async_stop_in_initial_action_skips_later_actions_and_notifications():
    log = []

    async def first():
        await service.send("GO")
        await service.stop()

    service = interpret_async(startup_machine(first, log))
    service.subscribe(lambda state: log.append(f"notify:{state.value}"))
    await service.start()
    assert service.status == "stopped"
    assert service.state.value == "a"
    assert log == []


def test_machine_actor_uses_startup_queue_boundary():
    log = []

    def first():
        log.append("initial:first")
        actor.send("GO")

    actor = create_actor(startup_machine(first, log))
    try:
        actor.start()
        assert actor.get_snapshot().value == "b"
        assert log == ["initial:first", "initial:second", "transition:GO"]
    finally:
        actor.stop()


async def test_async_timer_waits_for_initial_action(monkeypatch):
    log = []
    attempted, release = asyncio.Event(), asyncio.Event()

    async def first():
        log.append("initial:first")
        await release.wait()

    service = interpret_async(
        startup_machine(first, log, after={0: {"target": "b", "actions": "move"}})
    )
    original_send = service.send

    async def observed_send(event):
        attempted.set()
        return await original_send(event)

    monkeypatch.setattr(service, "send", observed_send)
    service.subscribe(lambda state: log.append(f"notify:{state.value}"))
    startup = asyncio.create_task(service.start())
    try:
        await asyncio.wait_for(attempted.wait(), 5)
        assert log == ["initial:first"]
        assert service.state.value == "a"
        release.set()
        await asyncio.wait_for(startup, 5)
        assert log == [
            "initial:first",
            "initial:second",
            "notify:a",
            "transition:GO",
            "notify:b",
        ]
    finally:
        release.set()
        await service.stop()
        await asyncio.gather(startup, return_exceptions=True)


def test_sync_initial_subscriber_failure_discards_queued_send():
    log = []
    service = interpret(startup_machine(lambda: None, log))
    error = ValueError("subscriber failed")

    def observe(state):
        if state.value == "a":
            service.send("GO")
            raise error

    subscription = service.subscribe(observe)
    try:
        with pytest.raises(ValueError) as caught:
            service.start()
        assert caught.value is error
        assert service.state.value == "a"
        assert log == ["initial:second"]
        subscription.unsubscribe()
        assert service.send("GO").value == "b"
        assert log == ["initial:second", "transition:GO"]
    finally:
        service.stop()


async def test_async_stop_during_startup_resolves_concurrent_sender():
    log = []
    entered, release = asyncio.Event(), asyncio.Event()

    async def first():
        entered.set()
        await release.wait()

    service = interpret_async(startup_machine(first, log))
    startup = asyncio.create_task(service.start())
    try:
        await asyncio.wait_for(entered.wait(), 5)
        waiting = asyncio.create_task(service.send("GO"))
        await asyncio.sleep(0)
        await service.stop()
        assert (await asyncio.wait_for(waiting, 5)).value == "a"
        release.set()
        await asyncio.wait_for(startup, 5)
        assert service.status == "stopped"
        assert log == []
    finally:
        release.set()
        await service.stop()
        await asyncio.gather(startup, return_exceptions=True)


async def test_async_cancelled_drain_settles_following_events():
    entered = asyncio.Event()

    async def block():
        entered.set()
        await asyncio.Event().wait()

    machine = Machine(
        {
            "id": "cancelled-drain",
            "initial": "a",
            "states": {"a": {"on": {"BLOCK": {"actions": block}, "GO": "b"}}, "b": {}},
        }
    )
    service = await interpret_async(machine).start()
    active = asyncio.create_task(service.send("BLOCK"))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        waiting = asyncio.create_task(service.send("GO"))
        await asyncio.sleep(0)
        active.cancel()
        results = await asyncio.wait_for(
            asyncio.gather(active, waiting, return_exceptions=True), 5
        )
        assert all(isinstance(result, asyncio.CancelledError) for result in results)
        assert (await service.send("GO")).value == "b"
    finally:
        await service.stop()

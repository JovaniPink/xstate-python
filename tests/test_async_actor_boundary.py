"""The sync actor and async interpreter have distinct execution boundaries."""

import asyncio
import inspect
import warnings

import pytest

from xstate import (
    Machine,
    create_actor,
    from_promise,
    interpret,
    interpret_async,
    send_parent,
    send_to,
)


async def test_async_interpreter_warns_for_invoke_and_does_not_start_child():
    calls = []

    def fetch(input):
        calls.append(input)
        return 42

    machine = Machine(
        {
            "id": "fetch",
            "initial": "idle",
            "states": {
                "idle": {"on": {"GO": "loading"}},
                "loading": {
                    "invoke": {
                        "id": "fetcher",
                        "src": "fetcher",
                        "input": 21,
                        "onDone": "done",
                    }
                },
                "done": {"type": "final"},
            },
        },
        actors={"fetcher": from_promise(fetch)},
    )
    with pytest.warns(RuntimeWarning, match="does not start invoked actors"):
        service = interpret_async(machine)
    try:
        await service.start()
        await service.send("GO")
        assert service.state.value == "loading"
        assert calls == []
        # Applications can still explicitly supply an event themselves.
        await service.send("done.invoke.fetcher")
        assert service.state.value == "done"
    finally:
        await service.stop()


@pytest.mark.parametrize("action", [send_parent("PING"), send_to("worker", "PING")])
async def test_async_interpreter_warns_when_actor_messages_cannot_be_routed(action):
    machine = Machine(
        {
            "id": "message",
            "initial": "idle",
            "states": {
                "idle": {"on": {"GO": {"target": "done", "actions": [action]}}},
                "done": {},
            },
        }
    )
    service = await interpret_async(machine).start()
    try:
        with pytest.warns(RuntimeWarning, match="cannot route actor messages"):
            await service.send("GO")
        assert service.state.value == "done"
    finally:
        await service.stop()


@pytest.mark.parametrize("make_service", [interpret, create_actor])
def test_sync_machine_runtime_warns_for_awaitable_action(make_service):
    calls = []

    async def effect():
        calls.append("ran")

    machine = Machine(
        {
            "id": "sync",
            "initial": "idle",
            "states": {
                "idle": {"on": {"GO": {"target": "done", "actions": [effect]}}},
                "done": {},
            },
        }
    )
    service = make_service(machine).start()
    try:
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always", RuntimeWarning)
            service.send("GO")
        assert any("does not await action results" in str(w.message) for w in captured)
        snapshot = (
            service.get_snapshot() if make_service is create_actor else service.state
        )
        assert snapshot.value == "done"
        assert calls == []
    finally:
        service.stop()


async def test_sync_runtime_does_not_cancel_a_returned_task():
    completed = []
    tasks = []

    async def background():
        await asyncio.sleep(0)
        completed.append(True)

    def schedule():
        task = asyncio.create_task(background())
        tasks.append(task)
        return task

    machine = Machine(
        {"id": "task", "initial": "idle", "states": {"idle": {"entry": [schedule]}}}
    )
    actor = create_actor(machine)
    try:
        with pytest.warns(RuntimeWarning, match="does not await action results"):
            actor.start()
        await tasks[0]
        assert completed == [True]
        assert not tasks[0].cancelled()
    finally:
        actor.stop()


def test_warning_as_error_keeps_committed_snapshot_and_coroutine_ownership():
    returned = []

    async def effect():
        pass

    def make_coroutine():
        coroutine = effect()
        returned.append(coroutine)
        return coroutine

    machine = Machine(
        {
            "id": "warning-error",
            "initial": "idle",
            "states": {
                "idle": {"on": {"GO": {"target": "next", "actions": [make_coroutine]}}},
                "next": {"on": {"FINISH": "done"}},
                "done": {},
            },
        }
    )
    service = interpret(machine).start()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            with pytest.raises(RuntimeWarning, match="does not await action results"):
                service.send("GO")
        assert service.state.value == "next"
        assert inspect.getcoroutinestate(returned[0]) == inspect.CORO_CREATED
        service.send("FINISH")
        assert service.state.value == "done"
    finally:
        for coroutine in returned:
            coroutine.close()
        service.stop()


async def test_sync_runtime_does_not_close_an_application_owned_coroutine():
    completed = []
    tasks = []

    async def background():
        await asyncio.sleep(0)
        completed.append(True)

    def schedule():
        coroutine = background()
        tasks.append(asyncio.create_task(coroutine))
        return coroutine

    machine = Machine(
        {"id": "owned", "initial": "idle", "states": {"idle": {"entry": [schedule]}}}
    )
    actor = create_actor(machine)
    try:
        with pytest.warns(RuntimeWarning, match="does not await action results"):
            actor.start()
        await tasks[0]
        assert completed == [True]
    finally:
        actor.stop()


async def test_async_interpreter_awaits_actions_without_spurious_warning():
    calls = []

    async def effect():
        await asyncio.sleep(0)
        calls.append("ran")

    machine = Machine(
        {"id": "async", "initial": "idle", "states": {"idle": {"entry": [effect]}}}
    )
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", RuntimeWarning)
        service = await interpret_async(machine).start()
        await service.stop()
    assert calls == ["ran"]
    assert not captured


async def test_invoked_async_child_requires_loop_on_starting_thread():
    async def fetch(input):
        return 42

    machine = Machine(
        {
            "id": "thread-boundary",
            "initial": "idle",
            "states": {
                "idle": {"on": {"GO": "loading"}},
                "loading": {"invoke": {"id": "fetch", "src": "fetch"}},
            },
        },
        actors={"fetch": from_promise(fetch)},
    )
    actor = create_actor(machine).start()
    try:
        # The main thread has an event loop, but the thread processing this
        # event does not. The destination snapshot is already installed.
        with pytest.raises(RuntimeError, match="requires a running event loop"):
            await asyncio.to_thread(actor.send, "GO")
        assert actor.get_snapshot().value == "loading"
    finally:
        actor.stop()

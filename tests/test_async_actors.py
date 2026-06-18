"""Tests for async actor logic (0.5.0).

Covers coroutine ``from_promise`` resolution on the event loop,
``from_observable`` streaming, ``to_promise`` adaptation, async ``invoke``
integration with a machine parent, and the running-loop requirement.
"""

import asyncio

import pytest

from xstate import (
    Machine,
    assign,
    create_actor,
    from_observable,
    from_promise,
    to_promise,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _wait_for(predicate, timeout: float = 1.0) -> None:
    """Poll until *predicate* is true or *timeout* (seconds) elapses."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError("condition not met within timeout")
        await asyncio.sleep(0.005)


def _fetch_machine(fetcher):
    return Machine(
        {
            "id": "fetcher_parent",
            "context": {"result": None, "error": None},
            "initial": "loading",
            "states": {
                "loading": {
                    "invoke": {
                        "id": "fetch",
                        "src": "fetcher",
                        "onDone": {
                            "target": "success",
                            "actions": [assign({"result": lambda c, e: e.data})],
                        },
                        "onError": {
                            "target": "failure",
                            "actions": [assign({"error": lambda c, e: str(e.data)})],
                        },
                    }
                },
                "success": {},
                "failure": {},
            },
        },
        actors={"fetcher": fetcher},
    )


# ---------------------------------------------------------------------------
# async from_promise
# ---------------------------------------------------------------------------


async def test_async_promise_resolves_with_output():
    async def fetch(input):
        await asyncio.sleep(0)
        return 42

    actor = create_actor(from_promise(fetch)).start()
    # Not resolved synchronously: the coroutine runs on the loop.
    assert actor.get_snapshot().status == "active"
    result = await to_promise(actor)
    assert result == 42
    assert actor.get_snapshot().status == "done"


async def test_async_promise_receives_input():
    async def double(input):
        await asyncio.sleep(0)
        return input * 2

    actor = create_actor(from_promise(double), input=21).start()
    assert await to_promise(actor) == 42


async def test_async_promise_rejects_into_error():
    async def boom(input):
        await asyncio.sleep(0)
        raise ValueError("nope")

    actor = create_actor(from_promise(boom)).start()
    with pytest.raises(ValueError, match="nope"):
        await to_promise(actor)
    snap = actor.get_snapshot()
    assert snap.status == "error"
    assert isinstance(snap.error, ValueError)


async def test_stop_cancels_pending_async_promise():
    started = asyncio.Event()

    async def slow(input):
        started.set()
        await asyncio.sleep(10)
        return "done"

    actor = create_actor(from_promise(slow)).start()
    await started.wait()
    actor.stop()
    assert actor.status == "stopped"
    await asyncio.sleep(0.01)
    # Never resolved — the task was cancelled.
    assert actor.get_snapshot().status == "active"


# ---------------------------------------------------------------------------
# to_promise
# ---------------------------------------------------------------------------


async def test_to_promise_on_already_resolved_sync_actor():
    # A plain (sync) from_promise resolves eagerly on start.
    actor = create_actor(from_promise(lambda input: 7)).start()
    assert actor.get_snapshot().status == "done"
    assert await to_promise(actor) == 7


async def test_to_promise_raises_on_sync_actor_error():
    def boom(input):
        raise RuntimeError("sync boom")

    actor = create_actor(from_promise(boom)).start()
    with pytest.raises(RuntimeError, match="sync boom"):
        await to_promise(actor)


# ---------------------------------------------------------------------------
# from_observable
# ---------------------------------------------------------------------------


async def test_observable_emits_values_then_done():
    async def numbers(input):
        for i in range(3):
            await asyncio.sleep(0)
            yield i

    emitted: list = []

    actor = create_actor(from_observable(numbers))
    actor.subscribe(
        lambda snap: (
            emitted.append(snap.context)
            if snap.status == "active" and snap.context is not None
            else None
        )
    )
    actor.start()
    result = await to_promise(actor)
    assert emitted == [0, 1, 2]
    assert result == 2  # output is the final emitted value
    assert actor.get_snapshot().status == "done"


async def test_observable_propagates_error():
    async def failing(input):
        yield 1
        raise RuntimeError("stream boom")

    actor = create_actor(from_observable(failing)).start()
    with pytest.raises(RuntimeError, match="stream boom"):
        await to_promise(actor)
    assert actor.get_snapshot().status == "error"


async def test_observable_receives_input():
    async def gen(input):
        for i in range(input):
            await asyncio.sleep(0)
            yield i

    actor = create_actor(from_observable(gen), input=2).start()
    assert await to_promise(actor) == 1  # last of range(2) -> 0, 1


# ---------------------------------------------------------------------------
# async invoke integration (machine parent)
# ---------------------------------------------------------------------------


async def test_invoke_async_promise_on_done():
    async def fetcher(input):
        await asyncio.sleep(0)
        return 99

    actor = create_actor(_fetch_machine(from_promise(fetcher))).start()
    # The parent does not resolve synchronously with an async child.
    assert actor.get_snapshot().value == "loading"
    await _wait_for(lambda: actor.get_snapshot().value == "success")
    assert actor.get_snapshot().context["result"] == 99


async def test_invoke_async_promise_on_error():
    async def boom(input):
        await asyncio.sleep(0)
        raise ValueError("kaboom")

    actor = create_actor(_fetch_machine(from_promise(boom))).start()
    await _wait_for(lambda: actor.get_snapshot().value == "failure")
    assert actor.get_snapshot().context["error"] == "kaboom"


# ---------------------------------------------------------------------------
# running-loop requirement (synchronous context)
# ---------------------------------------------------------------------------


def test_async_promise_without_running_loop_raises():
    async def fetch(input):
        return 1

    with pytest.raises(RuntimeError, match="running event loop"):
        create_actor(from_promise(fetch)).start()


def test_to_promise_without_running_loop_raises():
    actor = create_actor(from_promise(lambda input: 1)).start()
    with pytest.raises(RuntimeError, match="running event loop"):
        to_promise(actor)

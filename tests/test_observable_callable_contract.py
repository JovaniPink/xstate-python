"""Observable factories share the promise actor's input-binding contract."""

import asyncio
from collections.abc import AsyncIterable
from functools import partial

import pytest

from xstate import create_actor, from_observable, to_promise


async def _single(value):
    yield value


async def _collect(source, **options):
    actor = create_actor(from_observable(source), **options)
    snapshots = []
    actor.subscribe(snapshots.append)
    try:
        actor.start().start()
        result = await asyncio.wait_for(to_promise(actor), 1)
        assert actor.get_snapshot().status == "done"
        assert [snapshot.status for snapshot in snapshots] == [
            *["active"] * (len(snapshots) - 1),
            "done",
        ]
        return [snapshot.context for snapshot in snapshots[:-1]], result
    finally:
        actor.stop()


@pytest.mark.parametrize("positional_only", [False, True])
async def test_positional_factory_receives_input_once_and_emits(positional_only):
    calls = []

    async def values(count: int) -> AsyncIterable[int]:
        for value in range(count):
            yield value

    def ordinary(count: int) -> AsyncIterable[int]:
        calls.append(count)
        return values(count)

    def only(count: int, /) -> AsyncIterable[int]:
        calls.append(count)
        return values(count)

    factory = only if positional_only else ordinary
    actor = create_actor(from_observable(factory), input=3)
    emissions = []
    actor.subscribe(
        lambda snapshot: (
            emissions.append(snapshot.context) if snapshot.status == "active" else None
        )
    )
    try:
        actor.start().start()
        assert await asyncio.wait_for(to_promise(actor), 1) == 2
        assert actor.get_snapshot().status == "done"
        assert emissions == [0, 1, 2]
        assert calls == [3]
    finally:
        actor.stop()


@pytest.mark.parametrize(
    "form",
    [
        "named",
        "named_positional_only",
        "keyword_only",
        "kwargs",
        "zero",
        "bound",
        "partial",
        "opaque",
    ],
)
async def test_supported_factory_forms_preserve_input_and_call_once(form):
    calls = []

    def record(value):
        calls.append(value)
        return _single(value)

    def named(input):
        return record(input)

    def named_positional_only(input, /):
        return record(input)

    def keyword_only(*, input):
        return record(input)

    def kwargs_only(**kwargs):
        return record(kwargs["input"])

    def zero():
        return record(42)

    class Source:
        def values(self, count):
            return record(count)

    def offset(count, increment):
        return record(count + increment)

    class Opaque:
        @property
        def __signature__(self):
            raise ValueError("no signature")

        def __call__(self, count):
            return record(count)

    factories = {
        "named": named,
        "named_positional_only": named_positional_only,
        "keyword_only": keyword_only,
        "kwargs": kwargs_only,
        "zero": zero,
        "bound": Source().values,
        "partial": partial(offset, increment=0),
        "opaque": Opaque(),
    }
    assert await _collect(factories[form], input=42) == ([42], 42)
    assert calls == [42]


@pytest.mark.parametrize("form", ["optional", "variadic"])
@pytest.mark.parametrize("options, expected", [({}, None), ({"input": 42}, 42)])
async def test_optional_and_variadic_factories_receive_actor_input(
    form, options, expected
):
    calls = []

    def optional(value=9, **kwargs):
        calls.append(((value,), kwargs))
        return _single(value)

    def variadic(*args, **kwargs):
        calls.append((args, kwargs))
        return _single(args[0])

    factory = optional if form == "optional" else variadic
    assert await _collect(factory, **options) == ([expected], expected)
    assert calls == [((expected,), {})]


async def test_named_input_keeps_keyword_precedence_over_optional_positional():
    calls = []

    def factory(value=9, *, input):
        calls.append((value, input))
        return _single(input)

    assert await _collect(factory, input=42) == ([42], 42)
    assert calls == [(9, 42)]


async def test_direct_async_iterable_still_emits_without_a_factory():
    async def values():
        yield 4
        yield 2

    assert await _collect(values(), input="unused") == ([4, 2], 2)


@pytest.mark.parametrize("form", ["positional", "keyword", "opaque"])
async def test_original_factory_type_error_is_preserved_without_retry(form):
    calls = []
    error = TypeError("inside observable factory")

    def fail(count):
        calls.append(count)
        raise error

    def keyword(*, input):
        return fail(input)

    class Opaque:
        @property
        def __signature__(self):
            raise ValueError("no signature")

        def __call__(self, count):
            return fail(count)

    factory = {"positional": fail, "keyword": keyword, "opaque": Opaque()}[form]
    actor = create_actor(from_observable(factory), input=42)
    try:
        actor.start().start()
        with pytest.raises(TypeError) as raised:
            await to_promise(actor)
        assert raised.value is error
        assert actor.get_snapshot().error is error
        assert actor.get_snapshot().status == "error"
        assert calls == [42]
    finally:
        actor.stop()


async def test_unrecognized_required_keyword_remains_a_binding_error():
    calls = []

    def factory(*, count):
        calls.append(count)
        return _single(count)

    actor = create_actor(from_observable(factory), input=42)
    try:
        actor.start()
        with pytest.raises(TypeError, match="required keyword-only argument: 'count'"):
            await to_promise(actor)
        assert actor.get_snapshot().status == "error"
        assert calls == []
    finally:
        actor.stop()


async def test_async_generator_preserves_iteration_error_after_emission():
    error = RuntimeError("stream failed")
    calls = []

    async def values(count):
        calls.append(count)
        yield count
        raise error

    actor = create_actor(from_observable(values), input=42)
    snapshots = []
    actor.subscribe(snapshots.append)
    try:
        actor.start()
        with pytest.raises(RuntimeError) as raised:
            await asyncio.wait_for(to_promise(actor), 1)
        assert raised.value is error
        assert actor.get_snapshot().error is error
        assert [(snapshot.status, snapshot.context) for snapshot in snapshots] == [
            ("active", 42),
            ("error", None),
        ]
        assert calls == [42]
    finally:
        actor.stop()


async def test_stopping_positional_factory_cancels_stream_without_restarting():
    started = asyncio.Event()
    cancelled = asyncio.Event()
    pending = asyncio.get_running_loop().create_future()
    calls = []

    async def values(count):
        calls.append(count)
        try:
            yield count
            started.set()
            await pending
            yield "late"
        finally:
            cancelled.set()

    actor = create_actor(from_observable(values), input=42)
    snapshots = []
    actor.subscribe(snapshots.append)
    try:
        actor.start()
        await asyncio.wait_for(started.wait(), 1)
        actor.stop().start()
        await asyncio.wait_for(cancelled.wait(), 1)
        assert actor.status == "stopped"
        assert actor.system.get(actor.id) is None
        assert [(snapshot.status, snapshot.context) for snapshot in snapshots] == [
            ("active", 42)
        ]
        assert calls == [42]
    finally:
        actor.stop()

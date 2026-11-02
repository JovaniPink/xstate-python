"""Input binding for promise actors matches their public callable contract."""

from functools import partial

import pytest

from xstate import Machine, assign, create_actor, from_promise, to_promise


def test_positional_parameter_accepts_actor_input_regardless_of_name():
    def twice(value: int) -> int:
        return value * 2

    actor = create_actor(from_promise(twice), input=21).start()
    try:
        assert actor.get_snapshot().status == "done"
        assert actor.get_snapshot().output == 42
    finally:
        actor.stop()


def test_positional_only_and_optional_parameter_receive_actor_input():
    def positional_only(value, /):
        return value * 2

    def optional(value=5):
        return value * 2

    for fn in (positional_only, optional):
        actor = create_actor(from_promise(fn), input=21).start()
        try:
            assert actor.get_snapshot().status == "done"
            assert actor.get_snapshot().output == 42
        finally:
            actor.stop()


def test_bound_method_and_partial_accept_actor_input():
    class Doubler:
        def calculate(self, value):
            return value * 2

    def add(value, increment):
        return value + increment

    for fn, input_value in ((Doubler().calculate, 21), (partial(add, increment=2), 40)):
        actor = create_actor(from_promise(fn), input=input_value).start()
        try:
            assert actor.get_snapshot().status == "done"
            assert actor.get_snapshot().output == 42
        finally:
            actor.stop()


def test_legacy_named_input_zero_argument_and_keyword_forms_remain_supported():
    def named(input):
        return input

    def keyword_only(*, input):
        return input

    def kwargs_only(**kwargs):
        return kwargs["input"]

    for fn in (named, keyword_only, kwargs_only, lambda: 42):
        actor = create_actor(from_promise(fn), input=42).start()
        try:
            assert actor.get_snapshot().status == "done"
            assert actor.get_snapshot().output == 42
        finally:
            actor.stop()


def test_variadic_and_default_positional_parameters_receive_actor_input():
    def variadic(*args):
        return args

    def default_with_kwargs(value=9, **kwargs):
        return value, kwargs

    first = create_actor(from_promise(variadic), input=42).start()
    second = create_actor(from_promise(default_with_kwargs), input=42).start()
    try:
        assert first.get_snapshot().output == (42,)
        assert second.get_snapshot().output == (42, {})
    finally:
        first.stop()
        second.stop()


def test_explicit_input_parameter_retains_keyword_precedence():
    def with_explicit_input(value=9, *, input):
        return value, input

    actor = create_actor(from_promise(with_explicit_input), input=42).start()
    try:
        assert actor.get_snapshot().output == (9, 42)
    finally:
        actor.stop()


def test_handler_type_error_is_reported_without_retrying_handler():
    calls = []

    def fail(value):
        calls.append(value)
        raise TypeError("inside handler")

    actor = create_actor(from_promise(fail), input=21).start()
    try:
        assert calls == [21]
        assert actor.get_snapshot().status == "error"
        assert str(actor.get_snapshot().error) == "inside handler"
    finally:
        actor.stop()


async def test_async_handler_with_non_input_parameter_resolves():
    async def twice(value: int) -> int:
        return value * 2

    actor = create_actor(from_promise(twice), input=21).start()
    try:
        assert await to_promise(actor) == 42
    finally:
        actor.stop()


def test_named_promise_invoked_from_data_only_machine_receives_input():
    def twice(value):
        return value * 2

    machine = Machine(
        {
            "id": "job",
            "context": {"result": None},
            "initial": "loading",
            "states": {
                "loading": {
                    "invoke": {
                        "id": "worker",
                        "src": "double",
                        "input": 21,
                        "onDone": {"target": "done", "actions": "save"},
                    }
                },
                "done": {"type": "final"},
            },
        },
        actions={"save": assign({"result": lambda _ctx, event: event.data})},
        actors={"double": from_promise(twice)},
    )
    actor = create_actor(machine).start()
    try:
        assert actor.get_snapshot().value == "done"
        assert actor.get_snapshot().context["result"] == 42
    finally:
        actor.stop()


@pytest.mark.parametrize("value", [None, 0, "", {"value": 1}])
def test_falsy_and_none_inputs_are_forwarded(value):
    def identity(item):
        return item

    actor = create_actor(from_promise(identity), input=value).start()
    try:
        assert actor.get_snapshot().status == "done"
        assert actor.get_snapshot().output == value
    finally:
        actor.stop()

"""Deferred effects observe the context/event/params at their action position."""

import asyncio
from copy import deepcopy
from dataclasses import dataclass, replace

import pytest

from xstate import (
    Event,
    HandlerArgs,
    Machine,
    assign,
    choose,
    dataclass_context,
    get_microsteps,
    interpret,
    interpret_async,
    pure,
    raise_,
)

GO = {"type": "GO", "request": "outer-request"}


def tagged(label):
    return {"type": "record", "params": {"label": label}}


def observation(args: HandlerArgs):
    return (
        deepcopy(args.params),
        args.context["n"],
        args.event.name,
        deepcopy(args.event.data),
    )


def causal_machine(record):
    return Machine(
        {
            "id": "causal",
            "initial": "idle",
            "context": {"n": 0},
            "states": {
                "idle": {
                    "on": {
                        "GO": {
                            "target": "receiving",
                            "actions": [
                                tagged("before"),
                                assign({"n": 1}),
                                tagged("after"),
                                raise_("INNER"),
                            ],
                        }
                    }
                },
                "receiving": {
                    "on": {"INNER": {"target": "settling", "actions": tagged("raised")}}
                },
                "settling": {
                    "always": {"target": "accepted", "actions": tagged("eventless")}
                },
                "accepted": {},
            },
        },
        actions={"record": record},
    )


CAUSAL_OBSERVATIONS = [
    ({"label": "before"}, 0, "GO", GO),
    ({"label": "after"}, 1, "GO", GO),
    ({"label": "raised"}, 1, "INNER", None),
    ({"label": "eventless"}, 1, "INNER", None),
]


def test_pure_transition_defers_effects_with_their_causal_arguments():
    seen = []
    machine = causal_machine(lambda args: seen.append(observation(args)))
    initial = machine.initial_state

    result = machine.transition(initial, GO)

    assert seen == []
    assert initial.context == {"n": 0}
    assert result.value == "accepted"
    assert result.context == {"n": 1}
    for effect in result.actions:
        effect()
    assert seen == CAUSAL_OBSERVATIONS


def test_shared_named_and_inline_specs_keep_independent_transition_environments():
    seen = []

    def inline(args: HandlerArgs):
        seen.append(("inline", args.context["n"], args.event.data["request"]))

    shared = tagged("named")
    machine = Machine(
        {
            "id": "independent-emissions",
            "initial": "idle",
            "context": {"n": 0},
            "states": {
                "idle": {
                    "on": {
                        "GO": {
                            "actions": [
                                shared,
                                inline,
                                assign({"n": lambda args: args.event.data["n"]}),
                                shared,
                                inline,
                            ]
                        }
                    }
                }
            },
        },
        actions={
            "record": lambda args: seen.append(
                (args.params["label"], args.context["n"], args.event.data["request"])
            )
        },
    )
    initial = machine.initial_state
    first = machine.transition(initial, {"type": "GO", "n": 1, "request": "first"})
    second = machine.transition(initial, {"type": "GO", "n": 2, "request": "second"})
    assert seen == []
    # Execute in reverse evaluation order: the second evaluation must not rebind
    # a shared declaration that the first action list still references.
    for result in (second, first):
        for effect in result.actions:
            effect()
    assert seen == [
        ("named", 0, "second"),
        ("inline", 0, "second"),
        ("named", 2, "second"),
        ("inline", 2, "second"),
        ("named", 0, "first"),
        ("inline", 0, "first"),
        ("named", 1, "first"),
        ("inline", 1, "first"),
    ]
    assert initial.context == {"n": 0}


def test_opaque_event_and_literal_or_callable_params_retain_identity():
    class Opaque:
        def __deepcopy__(self, memo):
            raise AssertionError("Event payloads and params must not be copied")

    def parameter_payload(*args, **kwargs):
        raise AssertionError("Callable params are not an expression to evaluate")

    payload = Opaque()
    literal_params = {"opaque": Opaque()}
    event = Event("GO", payload)
    seen = []
    machine = Machine(
        {
            "id": "opaque-arguments",
            "initial": "idle",
            "context": {"n": 0},
            "states": {
                "idle": {
                    "on": {
                        "GO": {
                            "actions": [
                                {"type": "record", "params": literal_params},
                                assign({"n": 1}),
                                {"type": "record", "params": parameter_payload},
                            ]
                        }
                    }
                }
            },
        },
        actions={"record": lambda args: seen.append(args)},
    )
    result = machine.transition(machine.initial_state, event)
    assert seen == []
    for effect in result.actions:
        effect()
    assert [args.context["n"] for args in seen] == [0, 1]
    assert all(args.event is event and args.event.data is payload for args in seen)
    assert seen[0].params is literal_params
    assert seen[1].params is parameter_payload
    assert all(args.state is None for args in seen)


@pytest.mark.parametrize("traced", [False, True])
def test_sync_effect_arguments_do_not_depend_on_inspection(traced):
    seen = []
    traces = []
    service = interpret(
        causal_machine(lambda args: seen.append(observation(args))),
        inspect=traces.append if traced else None,
    ).start()
    try:
        service.send(GO)
        assert seen == CAUSAL_OBSERVATIONS
        assert service.state.context == {"n": 1}
        assert len(traces) == (2 if traced else 0)
    finally:
        service.stop()


@pytest.mark.parametrize("traced", [False, True])
async def test_async_effect_arguments_survive_await_and_inspection(traced):
    seen = []
    traces = []

    async def record(args: HandlerArgs):
        await asyncio.sleep(0)
        seen.append(observation(args))

    service = interpret_async(
        causal_machine(record), inspect=traces.append if traced else None
    )
    await service.start()
    try:
        await service.send(GO)
        assert seen == CAUSAL_OBSERVATIONS
        assert service.state.context == {"n": 1}
        assert len(traces) == (2 if traced else 0)
    finally:
        await service.stop()


def test_public_microstep_effects_have_the_same_arguments_as_macrostep_effects():
    seen = []
    machine = causal_machine(lambda args: seen.append(observation(args)))
    initial = machine.initial_state
    result = machine.transition(initial, GO)
    microsteps = get_microsteps(machine, initial, GO)

    assert seen == []
    for step in microsteps:
        for effect in step.snapshot.actions:
            effect()
    assert seen == CAUSAL_OBSERVATIONS
    seen.clear()
    for effect in result.actions:
        effect()
    assert seen == CAUSAL_OBSERVATIONS


def test_initial_entry_and_exit_transition_entry_actions_capture_each_assignment():
    seen = []
    machine = Machine(
        {
            "id": "entry-exit-causality",
            "initial": "left",
            "context": {"n": 0},
            "states": {
                "left": {
                    "initial": "child",
                    "entry": [tagged("initial-before"), assign({"n": 1})],
                    "exit": [tagged("parent-exit"), assign({"n": 3})],
                    "states": {
                        "child": {
                            "entry": tagged("initial-after"),
                            "exit": [tagged("child-exit"), assign({"n": 2})],
                            "on": {
                                "GO": {
                                    "target": "#right",
                                    "actions": [tagged("transition"), assign({"n": 4})],
                                }
                            },
                        }
                    },
                },
                "right": {
                    "id": "right",
                    "entry": [
                        tagged("entry-before"),
                        assign({"n": 5}),
                        tagged("entry-after"),
                    ],
                },
            },
        },
        actions={"record": lambda args: seen.append(observation(args))},
    )
    service = interpret(machine)
    assert seen == []
    try:
        service.start()
        assert seen == [
            ({"label": "initial-before"}, 0, "xstate.init", None),
            ({"label": "initial-after"}, 1, "xstate.init", None),
        ]
        seen.clear()
        service.send(GO)
        assert seen == [
            ({"label": "child-exit"}, 1, "GO", GO),
            ({"label": "parent-exit"}, 2, "GO", GO),
            ({"label": "transition"}, 3, "GO", GO),
            ({"label": "entry-before"}, 4, "GO", GO),
            ({"label": "entry-after"}, 5, "GO", GO),
        ]
        assert service.state.context == {"n": 5}
    finally:
        service.stop()


@pytest.mark.parametrize("regions", [("alpha", "beta"), ("beta", "alpha")])
def test_parallel_effects_keep_context_at_their_document_order_position(regions):
    seen = []
    states = {}
    for region in regions:
        states[region] = {
            "initial": "idle",
            "states": {
                "idle": {
                    "on": {
                        "GO": {
                            "target": "accepted",
                            "actions": [
                                tagged(f"{region}.before"),
                                assign({"n": lambda args: args.context["n"] + 1}),
                                tagged(f"{region}.after"),
                            ],
                        }
                    }
                },
                "accepted": {},
            },
        }
    machine = Machine(
        {
            "id": "parallel-causal",
            "type": "parallel",
            "context": {"n": 0},
            "states": states,
        },
        actions={"record": lambda args: seen.append(observation(args))},
    )
    service = interpret(machine).start()
    try:
        service.send(GO)
        assert seen == [
            ({"label": f"{regions[0]}.before"}, 0, "GO", GO),
            ({"label": f"{regions[0]}.after"}, 1, "GO", GO),
            ({"label": f"{regions[1]}.before"}, 1, "GO", GO),
            ({"label": f"{regions[1]}.after"}, 2, "GO", GO),
        ]
        assert service.state.context == {"n": 2}
    finally:
        service.stop()


def test_choose_and_pure_expansions_capture_each_emitted_effect_position():
    seen = []
    machine = Machine(
        {
            "id": "expanded-causality",
            "initial": "idle",
            "context": {"n": 0},
            "states": {
                "idle": {
                    "on": {
                        "GO": {
                            "actions": [
                                choose(
                                    [
                                        {
                                            "guard": lambda args: (
                                                args.context["n"] == 0
                                            ),
                                            "actions": [
                                                tagged("chosen-before"),
                                                assign({"n": 1}),
                                                tagged("chosen-after"),
                                            ],
                                        }
                                    ]
                                ),
                                pure(
                                    lambda args: [
                                        tagged(f"generated-at-{args.context['n']}"),
                                        assign({"n": 2}),
                                        tagged("generated-after"),
                                    ]
                                ),
                            ]
                        }
                    }
                }
            },
        },
        actions={"record": lambda args: seen.append(observation(args))},
    )
    result = machine.transition(machine.initial_state, GO)
    assert seen == []
    for effect in result.actions:
        effect()
    assert seen == [
        ({"label": "chosen-before"}, 0, "GO", GO),
        ({"label": "chosen-after"}, 1, "GO", GO),
        ({"label": "generated-at-1"}, 1, "GO", GO),
        ({"label": "generated-after"}, 2, "GO", GO),
    ]


def test_default_adapter_detaches_effect_context_before_nested_assignment_mutation():
    seen = []

    def mutate_assignment(args: HandlerArgs):
        args.context["items"].append("assigned")
        return {"n": 1}

    machine = Machine(
        {
            "id": "nested-isolation",
            "initial": "idle",
            "context": {"n": 0, "items": ["initial"]},
            "states": {
                "idle": {
                    "on": {
                        "GO": {
                            "actions": ["record", assign(mutate_assignment), "record"]
                        }
                    }
                }
            },
        },
        actions={"record": lambda args: seen.append(deepcopy(args.context))},
    )
    initial = machine.initial_state
    result = machine.transition(initial, GO)
    result.context["items"].append("after-transition")
    for effect in result.actions:
        effect()
    assert seen == [
        {"n": 0, "items": ["initial"]},
        {"n": 1, "items": ["initial", "assigned"]},
    ]
    assert initial.context == {"n": 0, "items": ["initial"]}
    assert result.context == {
        "n": 1,
        "items": ["initial", "assigned", "after-transition"],
    }


def test_mutating_one_effect_context_does_not_change_later_effects_or_state():
    seen = []

    def mutate(args: HandlerArgs):
        args.context["items"].append("effect-only")

    machine = Machine(
        {
            "id": "effect-isolation",
            "initial": "idle",
            "context": {"items": ["original"]},
            "states": {"idle": {"on": {"GO": {"actions": ["mutate", "record"]}}}},
        },
        actions={
            "mutate": mutate,
            "record": lambda args: seen.append(deepcopy(args.context)),
        },
    )
    service = interpret(machine).start()
    try:
        service.send(GO)
        assert seen == [{"items": ["original"]}]
        assert service.state.context == {"items": ["original"]}
    finally:
        service.stop()


@dataclass(frozen=True)
class ImmutableContext:
    n: int

    def __deepcopy__(self, memo):
        raise AssertionError("Use the configured context adapter")


class CustomContextAdapter:
    def snapshot(self, context):
        return replace(context)

    def apply(self, context, updates):
        return replace(context, **updates)


@pytest.mark.parametrize("adapter", [dataclass_context(), CustomContextAdapter()])
def test_causal_capture_respects_frozen_and_custom_context_adapters(adapter):
    seen = []
    machine = Machine(
        {
            "id": "adapter-causality",
            "initial": "idle",
            "context": ImmutableContext(0),
            "states": {
                "idle": {
                    "on": {"GO": {"actions": ["record", assign({"n": 1}), "record"]}}
                }
            },
        },
        context_adapter=adapter,
        actions={"record": lambda args: seen.append(args.context)},
    )
    result = machine.transition(machine.initial_state, GO)
    for effect in result.actions:
        effect()
    assert seen == [ImmutableContext(0), ImmutableContext(1)]
    assert result.context == ImmutableContext(1)


@pytest.mark.parametrize("adapter", [dataclass_context(), CustomContextAdapter()])
def test_pure_generated_choose_and_nested_pure_use_machine_bindings_and_adapter(
    adapter,
):
    seen = []
    generated = pure(
        lambda args: choose(
            [
                {
                    "guard": "zero",
                    "actions": [
                        tagged("before"),
                        "increment",
                        tagged("middle"),
                        pure(lambda args: ["increment", tagged("after")]),
                    ],
                }
            ]
        )
    )
    machine = Machine(
        {
            "id": "dynamic-adapter-causality",
            "initial": "idle",
            "context": ImmutableContext(0),
            "states": {"idle": {"on": {"GO": {"actions": generated}}}},
        },
        context_adapter=adapter,
        guards={"zero": lambda args: args.context.n == 0},
        actions={
            "increment": assign({"n": lambda args: args.context.n + 1}),
            "record": lambda args: seen.append(
                (args.params["label"], args.context.n, args.event.name)
            ),
        },
    )
    result = machine.transition(machine.initial_state, GO)
    assert seen == []
    for effect in result.actions:
        effect()
    assert seen == [("before", 0, "GO"), ("middle", 1, "GO"), ("after", 2, "GO")]
    assert result.context == ImmutableContext(2)


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_effect_failure_preserves_committed_state_and_causal_arguments(
    asynchronous,
):
    seen = []

    def fail(args: HandlerArgs):
        seen.append(("failure", args.context["n"], service.state.context["n"]))
        raise RuntimeError("effect failed")

    async def fail_async(args: HandlerArgs):
        await asyncio.sleep(0)
        fail(args)

    machine = Machine(
        {
            "id": "failure-causality",
            "initial": "idle",
            "context": {"n": 0},
            "states": {
                "idle": {
                    "on": {
                        "GO": {
                            "target": "committed",
                            "actions": [
                                tagged("before"),
                                assign({"n": 1}),
                                "fail",
                                tagged("after"),
                            ],
                        }
                    }
                },
                "committed": {},
            },
        },
        actions={
            "record": lambda args: seen.append(
                (args.params["label"], args.context["n"], service.state.context["n"])
            ),
            "fail": fail_async if asynchronous else fail,
        },
    )
    service = interpret_async(machine) if asynchronous else interpret(machine)
    if asynchronous:
        await service.start()
    else:
        service.start()
    try:
        with pytest.raises(RuntimeError, match="effect failed"):
            if asynchronous:
                await service.send(GO)
            else:
                service.send(GO)
        assert service.state.value == "committed"
        assert service.state.context == {"n": 1}
        assert seen == [("before", 0, 1), ("failure", 1, 1)]
    finally:
        if asynchronous:
            await service.stop()
        else:
            service.stop()

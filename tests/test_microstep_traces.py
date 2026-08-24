"""Public microstep traces, bounded execution, and interpreter inspection."""

from dataclasses import FrozenInstanceError

import pytest

from xstate import (
    InfiniteLoopError,
    Machine,
    MacrostepTrace,
    TransitionTrace,
    assign,
    create_actor,
    from_promise,
    get_initial_microsteps,
    get_microsteps,
    interpret,
    interpret_async,
    raise_,
)
from xstate.exceptions import InvalidConfigError


def _trace_machine(effects=None):
    effects = effects if effects is not None else []
    return Machine(
        {
            "id": "trace-machine",
            "initial": "idle",
            "states": {
                "idle": {
                    "on": {
                        "START": {
                            "target": "working",
                            "actions": [
                                "external",
                                raise_("IGNORED"),
                                raise_("NEXT"),
                            ],
                        }
                    }
                },
                "working": {"always": {"target": "ready", "actions": "eventless"}},
                "ready": {"on": {"NEXT": {"target": "done", "actions": "raised"}}},
                "done": {},
            },
        },
        actions={
            "external": lambda: effects.append("external"),
            "eventless": lambda: effects.append("eventless"),
            "raised": lambda: effects.append("raised"),
        },
    )


def test_get_microsteps_records_external_eventless_and_internal_fifo_order():
    effects = []
    machine = _trace_machine(effects)

    microsteps = get_microsteps(machine, machine.initial_state, "START")

    assert effects == []
    assert tuple(step.event.name for step in microsteps) == (
        "START",
        "START",
        "IGNORED",
        "NEXT",
    )
    assert tuple(len(step.transitions) for step in microsteps) == (1, 1, 0, 1)
    assert tuple(len(step.snapshot.actions) for step in microsteps) == (1, 1, 0, 1)
    assert tuple(step.snapshot.value for step in microsteps) == (
        "working",
        "ready",
        "ready",
        "done",
    )
    assert microsteps[0].transitions == (
        TransitionTrace(
            event_type="START",
            source_id="trace-machine.idle",
            target_ids=("trace-machine.working",),
        ),
    )
    assert microsteps[1].transitions[0].event_type == ""
    assert microsteps[3].transitions[0].event_type == "NEXT"


def test_intermediate_snapshots_and_trace_records_are_immutable():
    machine = _trace_machine()
    step = get_microsteps(machine, machine.initial_state, "START")[0]

    assert isinstance(step.snapshot.configuration, frozenset)
    assert isinstance(step.snapshot.actions, tuple)
    with pytest.raises(FrozenInstanceError):
        step.transitions = ()


def test_machine_transition_keeps_all_macrostep_actions():
    machine = _trace_machine()

    state = machine.transition(machine.initial_state, "START")

    assert state.value == "done"
    assert len(state.actions) == 3


def test_get_initial_microsteps_includes_initial_and_eventless_steps():
    machine = Machine(
        {
            "id": "initial-trace",
            "initial": "a",
            "states": {
                "a": {"entry": "enter-a", "always": "b"},
                "b": {"entry": "enter-b"},
            },
        },
        actions={"enter-a": lambda: None, "enter-b": lambda: None},
    )

    microsteps = get_initial_microsteps(machine)

    assert tuple(step.event.name for step in microsteps) == (
        "xstate.init",
        "xstate.init",
    )
    assert tuple(step.snapshot.value for step in microsteps) == ("a", "b")
    assert tuple(len(step.snapshot.actions) for step in microsteps) == (1, 1)


def test_eventless_cycle_stops_before_first_microstep_over_limit():
    executed = []

    def record(context, event):
        executed.append(event.name)
        return {}

    machine = Machine(
        {
            "id": "eventless-cycle",
            "initial": "a",
            "states": {
                "a": {"always": {"target": "b", "actions": assign(record)}},
                "b": {"always": {"target": "a", "actions": assign(record)}},
            },
        },
        max_iterations=3,
    )

    with pytest.raises(InfiniteLoopError) as exc_info:
        _ = machine.initial_state

    assert executed == ["xstate.init", "xstate.init"]
    assert str(exc_info.value) == (
        "Machine 'eventless-cycle' exceeded max iterations 3 for event 'xstate.init'."
    )


def test_raised_event_cycle_stops_at_exact_limit():
    executed = []

    def record(context, event):
        executed.append(event.name)
        return {}

    machine = Machine(
        {
            "id": "raised-cycle",
            "initial": "a",
            "states": {
                "a": {
                    "on": {
                        "START": {
                            "target": "b",
                            "actions": [assign(record), raise_("LOOP")],
                        }
                    }
                },
                "b": {
                    "on": {
                        "LOOP": {
                            "target": "b",
                            "actions": [assign(record), raise_("LOOP")],
                        }
                    }
                },
            },
        },
        max_iterations=3,
    )

    with pytest.raises(InfiniteLoopError, match="raised-cycle"):
        machine.transition(machine.initial_state, "START")

    assert executed == ["START", "LOOP", "LOOP"]


def test_unlimited_finite_eventless_execution_preserves_behavior():
    machine = Machine(
        {
            "id": "unlimited",
            "initial": "a",
            "states": {
                "a": {"always": "b"},
                "b": {"always": "c"},
                "c": {"always": "d"},
                "d": {},
            },
        }
    )

    assert machine.initial_state.value == "d"


def test_ignored_events_do_not_consume_iteration_limit():
    machine = Machine(
        {
            "id": "ignored-limit",
            "initial": "a",
            "states": {"a": {"on": {"GO": "b"}}, "b": {}},
        },
        max_iterations=1,
    )
    initial = machine.initial_state

    ignored = get_microsteps(machine, initial, "IGNORED")
    settled = machine.transition(initial, "GO")

    assert len(ignored) == 1
    assert ignored[0].transitions == ()
    assert settled.value == "b"


@pytest.mark.parametrize("value", [True, False, -1, 1.5, "2"])
def test_invalid_max_iterations_values_are_rejected(value):
    with pytest.raises(InvalidConfigError, match="maxIterations"):
        Machine(
            {
                "id": "invalid-limit",
                "initial": "a",
                "states": {"a": {}},
                "options": {"maxIterations": value},
            }
        )


def test_constructor_limit_overrides_json_option_only_when_non_none():
    config = {
        "id": "limit-precedence",
        "initial": "a",
        "states": {"a": {}},
        "options": {"maxIterations": 1},
    }

    assert Machine(config).max_iterations == 1
    assert Machine(config, max_iterations=None).max_iterations == 1
    assert Machine(config, max_iterations=4).max_iterations == 4


def _failing_transition_machine():
    return Machine(
        {
            "id": "transactional-limit",
            "initial": "a",
            "states": {
                "a": {"on": {"GO": "b"}},
                "b": {"always": "c"},
                "c": {},
            },
        },
        max_iterations=1,
    )


def test_sync_interpreter_keeps_committed_snapshot_when_limit_fails():
    service = interpret(_failing_transition_machine()).start()
    previous = service.state

    with pytest.raises(InfiniteLoopError):
        service.send("GO")

    assert service.state is previous
    assert service.state.value == "a"


async def test_async_interpreter_keeps_committed_snapshot_when_limit_fails():
    service = await interpret_async(_failing_transition_machine()).start()
    previous = service.state

    with pytest.raises(InfiniteLoopError):
        await service.send("GO")

    assert service.state is previous
    assert service.state.value == "a"


def _inspection_machine(log):
    return Machine(
        {
            "id": "inspection",
            "initial": "idle",
            "states": {
                "idle": {
                    "entry": "initial-action",
                    "on": {"GO": {"target": "done", "actions": "go-action"}},
                },
                "done": {},
            },
        },
        actions={
            "initial-action": lambda: log.append("initial-action"),
            "go-action": lambda: log.append("go-action"),
        },
    )


def test_sync_inspector_runs_after_install_before_actions_and_subscribers():
    log = []
    traces = []

    def inspect_trace(trace):
        assert isinstance(trace, MacrostepTrace)
        traces.append(trace)
        log.append(f"inspect:{trace.snapshot.value}")

    service = interpret(_inspection_machine(log), inspect=inspect_trace)
    service.subscribe(lambda state: log.append(f"subscribe:{state.value}"))
    service.start()
    service.send("GO")

    assert log == [
        "inspect:idle",
        "initial-action",
        "subscribe:idle",
        "inspect:done",
        "go-action",
        "subscribe:done",
    ]
    assert traces[0].previous_snapshot is None
    assert traces[0].event.name == "xstate.init"
    assert traces[1].previous_snapshot.value == "idle"
    assert traces[1].event.name == "GO"


def test_inspector_failure_warns_without_interrupting_behavior():
    effects = []

    def fail(_trace):
        raise RuntimeError("observer failed")

    service = interpret(_inspection_machine(effects), inspect=fail)

    with pytest.warns(RuntimeWarning, match="Inspector callback failed"):
        service.start()
    with pytest.warns(RuntimeWarning, match="Inspector callback failed"):
        state = service.send("GO")

    assert state.value == "done"
    assert effects == ["initial-action", "go-action"]


def _trace_signature(trace):
    return (
        trace.event.name,
        None if trace.previous_snapshot is None else trace.previous_snapshot.value,
        trace.snapshot.value,
        tuple(
            (step.event.name, step.snapshot.value, len(step.transitions))
            for step in trace.microsteps
        ),
    )


async def test_sync_and_async_inspectors_receive_equivalent_traces():
    sync_traces = []
    async_traces = []
    sync_service = interpret(_trace_machine(), inspect=sync_traces.append).start()
    sync_service.send("START")

    async_service = interpret_async(_trace_machine(), inspect=async_traces.append)
    await async_service.start()
    await async_service.send("START")

    assert tuple(map(_trace_signature, sync_traces)) == tuple(
        map(_trace_signature, async_traces)
    )


def test_machine_actor_accepts_inspector():
    traces = []
    actor = create_actor(_trace_machine(), inspect=traces.append).start()
    actor.send("START")

    assert tuple(trace.event.name for trace in traces) == ("xstate.init", "START")


def test_non_machine_actor_rejects_inspector():
    with pytest.raises(TypeError, match="inspect"):
        create_actor(from_promise(lambda: 1), inspect=lambda trace: None)

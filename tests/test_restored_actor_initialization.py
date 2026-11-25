"""A constructor-supplied checkpoint replaces fresh machine initialization."""

import pytest

from xstate import (
    Machine,
    SimulatedClock,
    assign,
    create_actor,
    deserialize_snapshot,
    from_callback,
)


class TrackingClock(SimulatedClock):
    def __init__(self):
        super().__init__()
        self.created = []

    def set_timeout(self, fn, delay_ms):
        self.created.append(delay_ms)
        return super().set_timeout(fn, delay_ms)


def _initializing_machine(calls, effects):
    def initialize(context, event):
        calls.append("assignment")
        return context["count"] + 1

    def can_finish(context, event):
        calls.append("guard")
        return True

    def output(context, event):
        calls.append("output")
        return {"count": context["count"]}

    return Machine(
        {
            "id": "restored-initialization",
            "context": {"count": 0},
            "initial": "fresh",
            "states": {
                "fresh": {
                    "entry": [
                        assign({"count": initialize}),
                        lambda: effects.append("fresh-entry"),
                    ],
                    "always": {"target": "done", "guard": can_finish},
                },
                "ready": {},
                "done": {"type": "final", "output": output},
            },
        }
    )


def _checkpoint(machine, *, status="active", count=10):
    return deserialize_snapshot(
        machine,
        {
            "value": "done" if status == "done" else "ready",
            "context": {"count": count},
            "status": status,
            "output": {"stored": count},
            "error": "saved error" if status == "error" else None,
        },
    )


@pytest.mark.parametrize("inspected", [False, True])
@pytest.mark.parametrize("status", ["active", "done", "error"])
def test_supplied_checkpoint_skips_initial_computation_and_is_visible_before_start(
    monkeypatch, inspected, status
):
    calls, effects, traces, notifications, initializations = [], [], [], [], []
    machine = _initializing_machine(calls, effects)
    restored = _checkpoint(machine, status=status)
    compute_initial = machine._initial_transition_core

    def record_initialization(*, capture_microsteps):
        initializations.append(capture_microsteps)
        return compute_initial(capture_microsteps=capture_microsteps)

    monkeypatch.setattr(machine, "_initial_transition_core", record_initialization)
    actor = create_actor(
        machine, snapshot=restored, inspect=traces.append if inspected else None
    )
    try:
        actor.subscribe(notifications.append)
        assert (initializations, calls) == ([], [])
        assert actor.get_snapshot() is restored
        assert actor.status == "not_started"
        assert actor.get_snapshot().status == status
        assert actor.get_snapshot().context == {"count": 10}
        assert restored.event is None
        assert traces == notifications == effects == []

        actor.start().start()

        assert (initializations, calls) == ([], [])
        assert actor.get_snapshot() is restored
        assert restored.status == status
        assert restored.output == ({"stored": 10} if status == "done" else None)
        assert restored.error == ("saved error" if status == "error" else None)
        assert restored.event.name == "xstate.init"
        assert notifications == [restored]
        assert effects == []
        assert len(traces) == int(inspected)
        if inspected:
            assert traces[0].event.name == "xstate.init"
            assert traces[0].previous_snapshot is None
            assert traces[0].snapshot is restored
            assert traces[0].microsteps == ()
        if status == "done":
            assert actor.status == "done"
            assert actor.send("IGNORED") is restored
        else:
            # This change does not redefine the runtime policy for error snapshots.
            assert actor.status == "running"
    finally:
        actor.stop()


@pytest.mark.parametrize("inspected", [False, True])
def test_default_actor_still_computes_initial_state_before_start(inspected):
    calls, effects, traces = [], [], []
    machine = _initializing_machine(calls, effects)
    actor = create_actor(machine, inspect=traces.append if inspected else None)
    try:
        assert calls == ["assignment", "guard", "output"]
        assert actor.get_snapshot().status == "done"
        assert actor.get_snapshot().output == {"count": 1}
        assert effects == traces == []

        actor.start().start()

        assert calls == ["assignment", "guard", "output"]
        assert effects == ["fresh-entry"]
        assert len(traces) == int(inspected)
        if inspected:
            assert traces[0].microsteps
    finally:
        actor.stop()


@pytest.mark.parametrize("inspected", [False, True])
def test_start_override_wins_over_constructor_snapshot(inspected):
    calls, effects, traces = [], [], []
    machine = _initializing_machine(calls, effects)
    supplied = _checkpoint(machine, status="done")
    override = _checkpoint(machine, count=25)
    actor = create_actor(
        machine, snapshot=supplied, inspect=traces.append if inspected else None
    )
    try:
        assert actor.get_snapshot() is supplied
        actor.start(override)

        assert actor.get_snapshot() is override
        assert override.context == {"count": 25}
        assert override.status == "active"
        assert calls == effects == []
        if inspected:
            assert len(traces) == 1
            assert traces[0].snapshot is override
            assert traces[0].microsteps == ()
    finally:
        actor.stop()


@pytest.mark.parametrize("inspected", [False, True])
def test_snapshot_supplied_only_at_start_does_not_undo_eager_initialization(inspected):
    calls, effects, traces = [], [], []
    machine = _initializing_machine(calls, effects)
    restored = _checkpoint(machine)
    actor = create_actor(machine, inspect=traces.append if inspected else None)
    try:
        assert calls == ["assignment", "guard", "output"]
        actor.start(restored)

        assert actor.get_snapshot() is restored
        assert calls == ["assignment", "guard", "output"]
        assert effects == []
        if inspected:
            assert len(traces) == 1
            assert traces[0].snapshot is restored
            assert traces[0].microsteps == ()
    finally:
        actor.stop()


@pytest.mark.parametrize("inspected", [False, True])
def test_restored_resources_start_once_and_reentrant_events_wait_for_notification(
    inspected,
):
    log, traces = [], []
    clock = TrackingClock()

    def worker(send_back):
        log.append("child-start")
        send_back("READY")
        return lambda: log.append("child-stop")

    def child_input(context, event):
        log.append(("input", context["count"], event.name))
        return context["count"]

    def delay(context, event):
        log.append(("delay", context["count"], event.name))
        return 50

    def inspect_trace(trace):
        traces.append(trace)
        log.append(("inspect", trace.event.name))

    machine = Machine(
        {
            "id": "restored-resources",
            "initial": "fresh",
            "states": {
                "fresh": {},
                "ready": {
                    "entry": lambda: log.append("restored-entry"),
                    "invoke": {
                        "id": "worker",
                        "src": from_callback(worker),
                        "input": child_input,
                    },
                    "after": {"WAIT": "done"},
                    "on": {"READY": {"actions": lambda: log.append("queued-action")}},
                },
                "done": {"type": "final"},
            },
        },
        delays={"WAIT": delay},
    )
    restored = _checkpoint(machine)
    actor = create_actor(
        machine,
        snapshot=restored,
        clock=clock,
        inspect=inspect_trace if inspected else None,
    )
    try:
        actor.subscribe(lambda snapshot: log.append(("notify", snapshot.value)))
        assert actor.get_snapshot() is restored
        clock.increment(100)
        assert log == traces == clock.created == []
        assert actor.children == {}

        actor.start().start()

        assert actor.get_snapshot().value == "ready"
        assert list(actor.children) == ["worker"]
        assert clock.created == [50]
        assert log.count("child-start") == 1
        assert "restored-entry" not in log
        assert ("input", 10, "xstate.init") in log
        assert ("delay", 10, "xstate.init") in log
        assert log.index("child-start") < log.index(("notify", "ready"))
        assert log.index(("notify", "ready")) < log.index("queued-action")
        if inspected:
            assert [trace.event.name for trace in traces] == ["xstate.init", "READY"]
            assert traces[0].microsteps == ()

        clock.increment(49)
        assert actor.get_snapshot().value == "ready"
        clock.increment(1)
        assert actor.status == actor.get_snapshot().status == "done"
        assert actor.children == {}
        assert log.count("child-stop") == 1
        assert clock.created == [50]
    finally:
        actor.stop()


@pytest.mark.parametrize("inspected", [False, True])
def test_raw_supplied_snapshot_keeps_its_existing_pending_actions(inspected):
    effects, traces = [], []
    machine = Machine(
        {
            "id": "pending-actions",
            "initial": "fresh",
            "states": {
                "fresh": {"on": {"GO": "ready"}},
                "ready": {"entry": lambda: effects.append("ready-entry")},
            },
        }
    )
    supplied = machine.transition(machine.initial_state, "GO")
    assert supplied.actions
    actor = create_actor(
        machine, snapshot=supplied, inspect=traces.append if inspected else None
    )
    try:
        assert actor.get_snapshot() is supplied
        assert effects == traces == []
        actor.start().start()
        assert effects == ["ready-entry"]
        if inspected:
            assert len(traces) == 1
            assert traces[0].microsteps == ()
    finally:
        actor.stop()


def test_completed_checkpoint_does_not_restart_final_resources():
    effects = []
    clock = TrackingClock()
    machine = Machine(
        {
            "id": "completed-checkpoint",
            "initial": "fresh",
            "states": {
                "fresh": {},
                "done": {
                    "type": "final",
                    "entry": lambda: effects.append("entry"),
                    "exit": lambda: effects.append("exit"),
                    "invoke": {"src": from_callback(lambda: effects.append("invoke"))},
                    "after": {50: "fresh"},
                },
            },
        }
    )
    restored = _checkpoint(machine, status="done")
    actor = create_actor(machine, snapshot=restored, clock=clock)
    try:
        assert actor.get_snapshot() is restored
        actor.start()
        assert actor.status == "done"
        assert actor.get_snapshot().output == {"stored": 10}
        clock.increment(100)
        assert effects == clock.created == []
        assert actor.children == {}
        assert actor.system.get(actor.id) is None
    finally:
        actor.stop()


def test_stopping_restored_actor_before_start_discards_work():
    calls, effects, traces = [], [], []
    machine = _initializing_machine(calls, effects)
    restored = _checkpoint(machine)
    actor = create_actor(machine, snapshot=restored, inspect=traces.append)

    actor.stop().start()

    assert actor.status == "stopped"
    assert actor.get_snapshot() is restored
    assert calls == effects == traces == []
    assert actor.system.get(actor.id) is None

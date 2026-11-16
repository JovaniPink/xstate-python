"""Reentry owns resource generations; root completion is a terminal boundary."""

import asyncio
from collections import Counter
from contextlib import suppress
from weakref import ref

import pytest

from xstate import (
    Machine,
    SimulatedClock,
    assign,
    create_actor,
    from_callback,
    from_promise,
    interpret,
    interpret_async,
    raise_,
    send,
)


class TrackingClock(SimulatedClock):
    """Observe resource ownership while retaining the native clock behavior."""

    def __init__(self):
        super().__init__()
        self.pending = set()
        self.created = []

    def set_timeout(self, fn, delay_ms):
        def fire():
            self.pending.discard(timer_id)
            fn()

        timer_id = super().set_timeout(fire, delay_ms)
        self.pending.add(timer_id)
        self.created.append(delay_ms)
        return timer_id

    def clear_timeout(self, timeout_id):
        self.pending.discard(timeout_id)
        super().clear_timeout(timeout_id)


class ControlledSleeps:
    """Release actual asyncio timer tasks without depending on elapsed time."""

    def __init__(self, monkeypatch):
        self.original_sleep = asyncio.sleep
        self.pending = []
        monkeypatch.setattr("xstate.async_interpreter.asyncio.sleep", self.sleep)

    async def sleep(self, seconds):
        if seconds == 0:
            await self.original_sleep(0)
            return
        future = asyncio.get_running_loop().create_future()
        self.pending.append((seconds, future))
        await future

    async def checkpoint(self):
        # One turn starts/cancels timer tasks; the next delivers their callbacks.
        await self.original_sleep(0)
        await self.original_sleep(0)


SELF_TRANSITIONS = [
    pytest.param({}, False, id="targetless"),
    pytest.param({"target": "waiting"}, False, id="default-self"),
    pytest.param(
        {"target": "waiting", "reenter": False}, False, id="explicit-retention"
    ),
    pytest.param({"target": "waiting", "reenter": True}, True, id="reentry"),
]


def timer_machine(transition, effects):
    return Machine(
        {
            "id": "reentry-timer",
            "initial": "waiting",
            "states": {
                "waiting": {
                    "entry": "enter",
                    "exit": "exit",
                    "after": {"1000": "elapsed"},
                    "on": {"TOUCH": {**transition, "actions": "touch"}},
                },
                "elapsed": {},
            },
        },
        actions={
            "enter": lambda: effects.append("enter"),
            "exit": lambda: effects.append("exit"),
            "touch": lambda: effects.append("touch"),
        },
    )


@pytest.mark.parametrize("transition,reenters", SELF_TRANSITIONS)
def test_after_deadline_resets_only_on_reentry(transition, reenters):
    clock = SimulatedClock()
    effects = []
    service = interpret(timer_machine(transition, effects), clock=clock).start()
    try:
        clock.increment(600)
        service.send("TOUCH")
        assert effects == (
            ["enter", "exit", "touch", "enter"] if reenters else ["enter", "touch"]
        )
        clock.increment(399)
        assert service.state.value == "waiting"
        clock.increment(1)
        assert service.state.value == ("waiting" if reenters else "elapsed")
        if reenters:
            clock.increment(599)
            assert service.state.value == "waiting"
            clock.increment(1)
            assert service.state.value == "elapsed"
    finally:
        service.stop()


@pytest.mark.parametrize("transition,reenters", SELF_TRANSITIONS)
async def test_async_after_task_resets_only_on_reentry(
    transition, reenters, monkeypatch
):
    sleeps = ControlledSleeps(monkeypatch)
    service = await interpret_async(timer_machine(transition, [])).start()
    try:
        await sleeps.checkpoint()
        assert len(sleeps.pending) == 1
        delay, original = sleeps.pending[0]
        assert delay == 1.0
        await service.send("TOUCH")
        await sleeps.checkpoint()
        assert original.cancelled() is reenters
        assert len(sleeps.pending) == (2 if reenters else 1)
        delay, current = sleeps.pending[-1]
        assert delay == 1.0
        assert not current.done()
        current.set_result(None)
        await sleeps.checkpoint()
        assert service.state.value == "elapsed"
    finally:
        await service.stop()


def generation_worker(events):
    next_generation = 0

    def worker(input):
        nonlocal next_generation
        next_generation += 1
        generation = next_generation
        events.append(("start", generation, input))
        return lambda: events.append(("stop", generation))

    return from_callback(worker)


def test_invoked_callback_reentry_replaces_generation_and_exit_cleans_once():
    events = []
    machine = Machine(
        {
            "id": "callback-generations",
            "initial": "active",
            "context": {"generation": 0},
            "states": {
                "active": {
                    "invoke": {
                        "id": "worker",
                        "src": "worker",
                        "input": lambda args: args.context["generation"],
                    },
                    "on": {
                        "REENTER": {
                            "target": "active",
                            "reenter": True,
                            "actions": assign({"generation": 1}),
                        },
                        "LEAVE": "idle",
                    },
                },
                "idle": {},
            },
        },
        actors={"worker": generation_worker(events)},
    )
    actor = create_actor(machine, clock=SimulatedClock()).start()
    try:
        first = actor.children["worker"]
        actor.send("REENTER")
        second = actor.children["worker"]
        assert second is not first
        assert first.status == "stopped"
        assert actor.system.get("worker") is second
        assert events == [("start", 1, 0), ("stop", 1), ("start", 2, 1)]
        actor.send("LEAVE")
        assert actor.get_snapshot().value == "idle"
        assert actor.children == {}
        assert actor.system.get("worker") is None
        assert second.status == "stopped"
        assert events == [
            ("start", 1, 0),
            ("stop", 1),
            ("start", 2, 1),
            ("stop", 2),
        ]
        actor.stop().stop()
        assert len(events) == 4
    finally:
        actor.stop()


@pytest.mark.parametrize(
    "transition,reenters",
    [
        pytest.param({"target": ".second"}, False, id="default-descendant"),
        pytest.param(
            {"target": ".second", "reenter": False}, False, id="retained-parent"
        ),
        pytest.param(
            {"target": ".second", "type": "internal"}, False, id="legacy-internal"
        ),
        pytest.param(
            {"target": ".second", "reenter": True}, True, id="reentered-parent"
        ),
    ],
)
def test_descendant_transition_preserves_parent_resources_unless_reentered(
    transition, reenters
):
    events = []
    clock = SimulatedClock()
    machine = Machine(
        {
            "id": "parent-resources",
            "initial": "active",
            "states": {
                "active": {
                    "initial": "first",
                    "states": {"first": {}, "second": {}},
                    "invoke": {"id": "worker", "src": "worker"},
                    "after": {"1000": "expired"},
                    "on": {"MOVE": transition},
                },
                "expired": {},
            },
        },
        actors={"worker": generation_worker(events)},
    )
    actor = create_actor(machine, clock=clock).start()
    try:
        original = actor.children["worker"]
        clock.increment(600)
        actor.send("MOVE")
        assert actor.get_snapshot().value == {"active": "second"}
        assert (actor.children["worker"] is original) is not reenters
        assert events == (
            [("start", 1, None), ("stop", 1), ("start", 2, None)]
            if reenters
            else [("start", 1, None)]
        )
        clock.increment(400)
        assert actor.get_snapshot().value == (
            {"active": "second"} if reenters else "expired"
        )
        if reenters:
            clock.increment(600)
            assert actor.get_snapshot().value == "expired"
        assert actor.children == {}
        assert events[-1] == ("stop", 2 if reenters else 1)
    finally:
        actor.stop()


def completion_machine(effects, outputs, *, final_effect=None):
    def output(args):
        outputs.append(args.event.name)
        return {"accepted": args.context["accepted"]}

    return Machine(
        {
            "id": "completion",
            "initial": "active",
            "context": {"accepted": 0},
            "exit": "root-exit",
            "after": {"5000": {"actions": "late"}},
            "on": {
                "REOPEN": {"target": ".active", "actions": "late"},
                "LATE": {"actions": "late"},
            },
            "states": {
                "active": {
                    "entry": send("LATE", delay=2000, id="owned-send"),
                    "on": {
                        "FINISH": {
                            "target": "finished",
                            "actions": assign({"accepted": 1}),
                        }
                    },
                },
                "finished": {
                    "type": "final",
                    "entry": ["terminal-entry", send("LATE"), final_effect]
                    if final_effect is not None
                    else ["terminal-entry", send("LATE")],
                    "exit": "terminal-exit",
                    "output": output,
                },
            },
        },
        actions={
            "root-exit": lambda: effects.append("root-exit"),
            "terminal-entry": lambda: effects.append("terminal-entry"),
            "terminal-exit": lambda: effects.append("terminal-exit"),
            "late": lambda: effects.append("late"),
        },
    )


def test_root_completion_ignores_raised_and_eventless_transitions_and_later_events():
    effects = []
    machine = Machine(
        {
            "id": "terminal-macrostep",
            "initial": "active",
            "on": {"REOPEN": ".active"},
            "exit": lambda: effects.append("root-exit"),
            "states": {
                "active": {
                    "on": {
                        "FINISH": {
                            "target": "finished",
                            "actions": raise_("REOPEN"),
                        }
                    }
                },
                "finished": {
                    "type": "final",
                    "entry": lambda: effects.append("terminal-entry"),
                    "exit": lambda: effects.append("terminal-exit"),
                    "output": {"accepted": True},
                    "always": "active",
                },
            },
        }
    )
    done = machine.transition(machine.initial_state, "FINISH")
    assert done.status == "done"
    assert done.value == "finished"
    assert done.output == {"accepted": True}
    assert effects == []
    for effect in done.actions:
        effect()
    assert effects == ["terminal-entry", "terminal-exit", "root-exit"]
    assert not done.can("REOPEN")
    ignored = machine.transition(done, "REOPEN")
    assert ignored.status == "done"
    assert ignored.value == done.value
    assert ignored.context == done.context
    assert ignored.output == done.output
    assert ignored.actions == ()


def test_sync_completion_runs_terminal_effects_once_and_releases_owned_timers():
    effects, outputs, snapshots = [], [], []
    clock = TrackingClock()
    service = interpret(completion_machine(effects, outputs), clock=clock).start()
    service.subscribe(lambda state: snapshots.append((state.value, state.status)))
    try:
        assert len(clock.pending) == 2
        service.send("FINISH")
        assert service.state.status == service.status == "done"
        assert service.state.output == {"accepted": 1}
        assert effects == ["terminal-entry", "terminal-exit", "root-exit"]
        assert outputs == ["FINISH"]
        assert clock.pending == set()
        assert snapshots == [("active", "active"), ("finished", "done")]
        service.send("REOPEN")
        service.start()
        clock.increment(5000)
        service.stop().stop()
        assert service.state.value == "finished"
        assert service.state.output == {"accepted": 1}
        assert effects == ["terminal-entry", "terminal-exit", "root-exit"]
        assert outputs == ["FINISH"]
        assert snapshots == [("active", "active"), ("finished", "done")]
    finally:
        service.stop()


async def test_async_completion_releases_timers_and_ignores_queued_events(monkeypatch):
    sleeps = ControlledSleeps(monkeypatch)
    effects, outputs, snapshots = [], [], []
    service = await interpret_async(completion_machine(effects, outputs)).start()
    service.subscribe(lambda state: snapshots.append((state.value, state.status)))
    try:
        await sleeps.checkpoint()
        assert len(sleeps.pending) == 2
        await service.send("FINISH")
        await sleeps.checkpoint()
        assert service.state.status == service.status == "done"
        assert service.state.output == {"accepted": 1}
        assert all(future.cancelled() for _, future in sleeps.pending)
        await service.send("REOPEN")
        await service.start()
        await service.stop()
        assert service.state.value == "finished"
        assert effects == ["terminal-entry", "terminal-exit", "root-exit"]
        assert outputs == ["FINISH"]
        assert snapshots == [("active", "active"), ("finished", "done")]
    finally:
        await service.stop()


async def test_async_final_effect_failure_still_completes_and_cancels_timers(
    monkeypatch,
):
    sleeps = ControlledSleeps(monkeypatch)
    effects, outputs, snapshots = [], [], []

    async def fail():
        effects.append("failed-effect")
        await asyncio.sleep(0)
        raise RuntimeError("terminal effect failed")

    service = await interpret_async(
        completion_machine(effects, outputs, final_effect=fail)
    ).start()
    service.subscribe(lambda state: snapshots.append(state.status))
    try:
        await sleeps.checkpoint()
        assert len(sleeps.pending) == 2
        with pytest.raises(RuntimeError, match="terminal effect failed"):
            await service.send("FINISH")
        await sleeps.checkpoint()
        assert service.state.status == service.status == "done"
        assert service.state.output == {"accepted": 1}
        assert all(future.cancelled() for _, future in sleeps.pending)
        await service.send("REOPEN")
        await service.start()
        assert effects.count("failed-effect") == 1
        assert "late" not in effects
        assert outputs == ["FINISH"]
        assert snapshots == ["active"]
    finally:
        await service.stop()


@pytest.mark.parametrize("raises", [False, True], ids=["complete", "effect-error"])
def test_final_machine_actor_cleans_and_unregisters_all_children_once(raises):
    started, cleaned = [], []

    def worker(input):
        started.append(input)
        return lambda: cleaned.append(input)

    def final_effect():
        if raises:
            raise RuntimeError("terminal effect failed")

    clock = TrackingClock()
    machine = Machine(
        {
            "id": "family",
            "initial": "active",
            "invoke": {"id": "root-worker", "src": "worker", "input": "root"},
            "after": {"5000": {"actions": lambda: None}},
            "on": {"REOPEN": ".active"},
            "states": {
                "active": {
                    "invoke": {
                        "id": "active-worker",
                        "src": "worker",
                        "input": "active",
                    },
                    "on": {"FINISH": "finished"},
                },
                "finished": {"type": "final", "entry": final_effect, "output": 7},
            },
        },
        actors={"worker": from_callback(worker)},
    )
    actor = create_actor(machine, id="parent", clock=clock).start()
    actor.spawn(from_callback(worker), id="manual-worker", input="manual").start()
    children = actor.children
    try:
        assert Counter(started) == Counter({"root": 1, "active": 1, "manual": 1})
        if raises:
            with pytest.raises(RuntimeError, match="terminal effect failed"):
                actor.send("FINISH")
        else:
            actor.send("FINISH")
        assert actor.get_snapshot().status == actor.status == "done"
        assert actor.get_snapshot().output == 7
        assert Counter(cleaned) == Counter({"root": 1, "active": 1, "manual": 1})
        assert clock.pending == set()
        assert actor.children == {}
        assert all(child.status == "stopped" for child in children.values())
        assert all(actor.system.get(child_id) is None for child_id in children)
        assert actor.system.get("parent") is None
        actor.send("REOPEN")
        actor.start()
        actor.stop().stop()
        assert actor.get_snapshot().value == "finished"
        assert Counter(cleaned) == Counter({"root": 1, "active": 1, "manual": 1})
    finally:
        actor.stop()


@pytest.mark.parametrize(
    "terminal,action_fails",
    [
        pytest.param(True, False, id="completion"),
        pytest.param(False, False, id="stop"),
        pytest.param(True, True, id="completion-and-action-failure"),
    ],
)
def test_cleanup_failure_still_disposes_entire_actor_family_once(
    terminal, action_fails
):
    cleaned = []
    send_backs = {}

    def worker(input, send_back):
        send_backs[input] = send_back

        def cleanup():
            cleaned.append(input)
            if input == "root":
                raise RuntimeError("cleanup failed")

        return cleanup

    def final_effect():
        if action_fails:
            raise RuntimeError("terminal effect failed")

    clock = TrackingClock()
    machine = Machine(
        {
            "id": "cleanup-failure",
            "initial": "active",
            "context": {"reports": 0},
            "invoke": {"id": "root-worker", "src": "worker", "input": "root"},
            "after": {"5000": {"actions": lambda: None}},
            "on": {
                "REPORT": {
                    "actions": assign(
                        {"reports": lambda args: args.context["reports"] + 1}
                    )
                }
            },
            "states": {
                "active": {
                    "invoke": {
                        "id": "active-worker",
                        "src": "worker",
                        "input": "active",
                    },
                    "on": {"FINISH": "finished"},
                },
                "finished": {
                    "type": "final",
                    "entry": final_effect,
                    "output": {"accepted": True},
                },
            },
        },
        actors={"worker": from_callback(worker)},
    )
    actor = create_actor(machine, id="parent", clock=clock).start()
    actor.spawn(from_callback(worker), id="manual-worker", input="manual").start()
    children = actor.children
    observed = []

    def observe(state):
        observed.append(state.status)

    observer_ref = ref(observe)
    actor.subscribe(observe)
    del observe
    observed.clear()
    try:
        assert set(send_backs) == {"root", "active", "manual"}
        message = "terminal effect failed" if action_fails else "cleanup failed"
        with pytest.raises(RuntimeError, match=f"^{message}$") as raised:
            if terminal:
                actor.send("FINISH")
            else:
                actor.stop()
        if action_fails:
            assert isinstance(raised.value.__cause__, RuntimeError)
            assert str(raised.value.__cause__) == "cleanup failed"
        assert Counter(cleaned) == Counter({"root": 1, "active": 1, "manual": 1})
        assert actor.status == ("done" if terminal else "stopped")
        assert actor.children == {}
        assert all(child.status == "stopped" for child in children.values())
        assert all(actor.system.get(child_id) is None for child_id in children)
        assert actor.system.get("parent") is None
        assert clock.pending == set()
        assert observed == []
        assert observer_ref() is None
        if terminal:
            assert actor.get_snapshot().status == "done"
            assert actor.get_snapshot().value == "finished"
            assert actor.get_snapshot().output == {"accepted": True}
        for send_back in send_backs.values():
            send_back("REPORT")
        assert actor.get_snapshot().context == {"reports": 0}
        actor.stop().stop()
        assert Counter(cleaned) == Counter({"root": 1, "active": 1, "manual": 1})
        if terminal:
            assert actor.get_snapshot().status == "done"
            assert actor.get_snapshot().output == {"accepted": True}
    finally:
        # A failing regression must not replace its assertion with another
        # cleanup exception during test teardown.
        for child in children.values():
            with suppress(RuntimeError):
                child.stop()
        with suppress(RuntimeError):
            actor.stop()


def test_initially_final_actor_runs_effects_once_without_starting_resources():
    effects = []
    clock = TrackingClock()

    def worker():
        effects.append("child-start")
        return lambda: effects.append("child-stop")

    machine = Machine(
        {
            "id": "initially-final",
            "initial": "finished",
            "entry": lambda: effects.append("root-entry"),
            "exit": lambda: effects.append("root-exit"),
            "invoke": {"id": "worker", "src": from_callback(worker)},
            "after": {"1000": {"actions": lambda: effects.append("timer")}},
            "states": {
                "finished": {
                    "type": "final",
                    "entry": lambda: effects.append("terminal-entry"),
                    "exit": lambda: effects.append("terminal-exit"),
                    "output": 17,
                }
            },
        }
    )
    actor = create_actor(machine, id="parent", clock=clock)
    try:
        assert effects == []
        actor.start().start()
        assert actor.get_snapshot().status == actor.status == "done"
        assert actor.get_snapshot().output == 17
        assert effects == ["root-entry", "terminal-entry", "terminal-exit", "root-exit"]
        assert clock.created == []
        assert actor.children == {}
        assert actor.system.get("parent") is None
        assert actor.system.get("worker") is None
        clock.increment(1000)
        actor.stop().start()
        assert effects == ["root-entry", "terminal-entry", "terminal-exit", "root-exit"]
    finally:
        actor.stop()


def test_parallel_root_final_leaves_exit_in_reverse_document_order():
    effects = []
    machine = Machine(
        {
            "id": "parallel-final",
            "type": "parallel",
            "exit": lambda: effects.append("root-exit"),
            "states": {
                "left": {
                    "type": "final",
                    "entry": lambda: effects.append("left-entry"),
                    "exit": lambda: effects.append("left-exit"),
                },
                "right": {
                    "type": "final",
                    "entry": lambda: effects.append("right-entry"),
                    "exit": lambda: effects.append("right-exit"),
                },
            },
        }
    )
    done = machine.initial_state
    assert done.status == "done"
    assert effects == []
    for effect in done.actions:
        effect()
    assert effects == [
        "left-entry",
        "right-entry",
        "right-exit",
        "left-exit",
        "root-exit",
    ]
    assert machine.transition(done, "IGNORED").actions == ()


@pytest.mark.parametrize("timer_kind", ["after", "delayed-send"])
async def test_completion_from_owned_timer_does_not_cancel_its_current_task(
    timer_kind, monkeypatch
):
    sleeps = ControlledSleeps(monkeypatch)
    terminal_tasks = []
    effects = []

    async def finish():
        terminal_tasks.append(asyncio.current_task())
        await asyncio.sleep(0)
        effects.append("finished")

    active = (
        {"after": {"1000": "finished"}}
        if timer_kind == "after"
        else {
            "entry": send("FINISH", delay=1000, id="finish"),
            "on": {"FINISH": "finished"},
        }
    )
    machine = Machine(
        {
            "id": "timer-completion",
            "initial": "active",
            "after": {"5000": {"actions": lambda: effects.append("late")}},
            "states": {
                "active": active,
                "finished": {"type": "final", "entry": finish, "output": 23},
            },
        }
    )
    service = await interpret_async(machine).start()
    try:
        await sleeps.checkpoint()
        assert len(sleeps.pending) == 2
        next(future for delay, future in sleeps.pending if delay == 1.0).set_result(
            None
        )
        await sleeps.checkpoint()
        assert len(terminal_tasks) == 1
        timer_task = terminal_tasks[0]
        await timer_task
        assert timer_task.done() and not timer_task.cancelled()
        assert service.state.status == service.status == "done"
        assert service.state.output == 23
        assert effects == ["finished"]
        assert next(
            future for delay, future in sleeps.pending if delay == 5.0
        ).cancelled()
    finally:
        await service.stop()


def test_callback_cleanup_can_send_but_stopped_generation_cannot_emit_later():
    send_backs = []

    def report(generation, phase):
        return {"type": "REPORT", "generation": generation, "phase": phase}

    def worker(send_back):
        send_backs.append(send_back)
        generation = len(send_backs)
        return lambda: send_back(report(generation, "cleanup"))

    machine = Machine(
        {
            "id": "callback-messages",
            "initial": "active",
            "context": {"reports": []},
            "on": {
                "REPORT": {
                    "actions": assign(
                        {
                            "reports": lambda args: [
                                *args.context["reports"],
                                (
                                    args.event.data["generation"],
                                    args.event.data["phase"],
                                ),
                            ]
                        }
                    )
                }
            },
            "states": {
                "active": {
                    "invoke": {"id": "worker", "src": from_callback(worker)},
                    "on": {
                        "REENTER": {
                            "target": "active",
                            "reenter": True,
                            "actions": lambda: send_backs[0](report(1, "queued")),
                        }
                    },
                }
            },
        }
    )
    actor = create_actor(machine, clock=SimulatedClock()).start()
    try:
        original = actor.children["worker"]
        actor.send("REENTER")
        assert original.status == "stopped"
        assert len(send_backs) == 2
        assert actor.get_snapshot().context["reports"] == [
            (1, "queued"),
            (1, "cleanup"),
        ]
        send_backs[0](report(1, "late"))
        assert actor.get_snapshot().context["reports"] == [
            (1, "queued"),
            (1, "cleanup"),
        ]
        send_backs[1](report(2, "current"))
        assert actor.get_snapshot().context["reports"] == [
            (1, "queued"),
            (1, "cleanup"),
            (2, "current"),
        ]
    finally:
        actor.stop()


async def test_stale_promise_completion_cannot_finish_new_invocation_generation():
    requests = []

    async def worker(input):
        result = asyncio.get_running_loop().create_future()
        requests.append(result)
        try:
            return await asyncio.shield(result)
        except asyncio.CancelledError:
            # Deliberately model an external operation that finishes after its
            # owner is stopped. Its result must not belong to the new child.
            return await result

    machine = Machine(
        {
            "id": "stale-completion",
            "initial": "loading",
            "context": {"result": None},
            "states": {
                "loading": {
                    "invoke": {
                        "id": "request",
                        "src": "worker",
                        "onDone": {
                            "target": "finished",
                            "actions": assign({"result": lambda args: args.event.data}),
                        },
                    },
                    "on": {"REENTER": {"target": "loading", "reenter": True}},
                },
                "finished": {"type": "final"},
            },
        },
        actors={"worker": from_promise(worker)},
    )
    actor = create_actor(machine, clock=SimulatedClock()).start()
    try:
        await asyncio.sleep(0)
        first = actor.children["request"]
        actor.send("REENTER")
        await asyncio.sleep(0)
        second = actor.children["request"]
        assert first is not second
        assert first.status == "stopped"
        assert len(requests) == 2
        requests[0].set_result("stale")
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert actor.get_snapshot().value == "loading"
        assert actor.get_snapshot().context == {"result": None}
        assert actor.children["request"] is second
        requests[1].set_result("current")
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert actor.get_snapshot().status == "done"
        assert actor.get_snapshot().context == {"result": "current"}
    finally:
        for result in requests:
            if not result.done():
                result.set_result("cleanup")
        actor.stop()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

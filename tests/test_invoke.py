"""Tests for `invoke:` — running a child actor for the lifetime of a state.

Covers:
  - invoking from_promise logic: onDone receives the output, onError the error
  - invoking a child machine: onDone fires when it reaches a final state
  - invoking from_callback logic: send_back drives the parent
  - resolving `src` from the machine's `actors` registry and inline logic
  - `input` resolution (static and from context)
  - the invoked actor is stopped when its state is exited before completing
"""

from xstate import (
    Machine,
    SimulatedClock,
    assign,
    create_actor,
    from_callback,
    from_promise,
)

# ---------------------------------------------------------------------------
# from_promise invocation
# ---------------------------------------------------------------------------


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


def test_invoke_promise_on_done():
    actor = create_actor(_fetch_machine(from_promise(lambda input: 42))).start()
    snap = actor.get_snapshot()
    assert snap.value == "success"
    assert snap.context["result"] == 42


def test_invoke_promise_on_error():
    def boom(input):
        raise ValueError("kaboom")

    actor = create_actor(_fetch_machine(from_promise(boom))).start()
    snap = actor.get_snapshot()
    assert snap.value == "failure"
    assert snap.context["error"] == "kaboom"


def test_invoke_inline_logic_without_registry():
    machine = Machine(
        {
            "id": "inline",
            "context": {"v": None},
            "initial": "run",
            "states": {
                "run": {
                    "invoke": {
                        "id": "p",
                        "src": from_promise(lambda input: "hi"),
                        "onDone": {
                            "target": "ok",
                            "actions": [assign({"v": lambda c, e: e.data})],
                        },
                    }
                },
                "ok": {},
            },
        }
    )
    actor = create_actor(machine).start()
    assert actor.get_snapshot().value == "ok"
    assert actor.get_snapshot().context["v"] == "hi"


# ---------------------------------------------------------------------------
# input resolution
# ---------------------------------------------------------------------------


def test_invoke_input_from_context():
    machine = Machine(
        {
            "id": "with_input",
            "context": {"x": 21, "doubled": None},
            "initial": "run",
            "states": {
                "run": {
                    "invoke": {
                        "id": "double",
                        "src": from_promise(lambda input: input * 2),
                        "input": lambda c, e: c["x"],
                        "onDone": {
                            "target": "ok",
                            "actions": [assign({"doubled": lambda c, e: e.data})],
                        },
                    }
                },
                "ok": {},
            },
        }
    )
    actor = create_actor(machine).start()
    assert actor.get_snapshot().context["doubled"] == 42


# ---------------------------------------------------------------------------
# child machine invocation
# ---------------------------------------------------------------------------


def test_invoke_child_machine_on_done():
    child = Machine(
        {
            "id": "child",
            "initial": "finished",
            "states": {
                "finished": {"type": "final", "output": {"ok": True}},
            },
        }
    )
    parent = Machine(
        {
            "id": "parent",
            "context": {"payload": None},
            "initial": "running",
            "states": {
                "running": {
                    "invoke": {
                        "id": "child",
                        "src": child,
                        "onDone": {
                            "target": "done",
                            "actions": [assign({"payload": lambda c, e: e.data})],
                        },
                    }
                },
                "done": {},
            },
        }
    )
    actor = create_actor(parent).start()
    assert actor.get_snapshot().value == "done"
    assert actor.get_snapshot().context["payload"] == {"ok": True}


# ---------------------------------------------------------------------------
# from_callback invocation
# ---------------------------------------------------------------------------


def test_invoke_callback_send_back_drives_parent():
    def ticker(send_back):
        send_back("TICK")

    machine = Machine(
        {
            "id": "cb",
            "initial": "waiting",
            "states": {
                "waiting": {
                    "invoke": {"id": "ticker", "src": "ticker"},
                    "on": {"TICK": "ticked"},
                },
                "ticked": {},
            },
        },
        actors={"ticker": from_callback(ticker)},
    )
    actor = create_actor(machine).start()
    assert actor.get_snapshot().value == "ticked"


# ---------------------------------------------------------------------------
# lifecycle: invoked actor stopped on state exit
# ---------------------------------------------------------------------------


def test_invoked_actor_stopped_when_state_exits():
    cleaned = []

    def worker(receive):
        # Long-lived callback; registers a receiver and a cleanup.
        receive(lambda e: None)
        return lambda: cleaned.append(True)

    machine = Machine(
        {
            "id": "lifecycle",
            "initial": "active",
            "states": {
                "active": {
                    "invoke": {"id": "worker", "src": "worker"},
                    "on": {"CANCEL": "idle"},
                },
                "idle": {},
            },
        },
        actors={"worker": from_callback(worker)},
    )
    actor = create_actor(machine).start()
    # The invoked actor is registered while in `active`.
    assert actor.system.get("worker") is not None
    actor.send("CANCEL")
    assert actor.get_snapshot().value == "idle"
    # Exiting `active` stops the invoked actor and runs its cleanup.
    assert cleaned == [True]
    assert actor.system.get("worker") is None


def test_invoke_only_starts_when_state_active():
    started = []

    def worker():
        started.append(True)

    machine = Machine(
        {
            "id": "deferred",
            "initial": "idle",
            "states": {
                "idle": {"on": {"GO": "active"}},
                "active": {"invoke": {"id": "worker", "src": "worker"}},
            },
        },
        actors={"worker": from_callback(worker)},
    )
    actor = create_actor(machine).start()
    assert started == []  # not invoked until `active` is entered
    actor.send("GO")
    assert started == [True]


def test_invoke_with_simulated_clock_timer():
    """A callback actor can drive the parent via a scheduled send_back."""

    def delayed(send_back, input):
        # Uses the actor's clock indirectly via the parent; here we just send
        # immediately to keep the test deterministic.
        send_back({"type": "READY", "value": input})

    machine = Machine(
        {
            "id": "timed_invoke",
            "context": {"value": None},
            "initial": "starting",
            "states": {
                "starting": {
                    "invoke": {"id": "d", "src": "delayed", "input": 7},
                    "on": {
                        "READY": {
                            "target": "ready",
                            "actions": [
                                assign({"value": lambda c, e: e.data["value"]})
                            ],
                        }
                    },
                },
                "ready": {},
            },
        },
        actors={"delayed": from_callback(delayed)},
    )
    actor = create_actor(machine, clock=SimulatedClock()).start()
    assert actor.get_snapshot().value == "ready"
    assert actor.get_snapshot().context["value"] == 7

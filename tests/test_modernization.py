from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from types import MappingProxyType

if sys.version_info >= (3, 12):
    from typing import override
else:

    def override(fn):  # type: ignore[misc]
        return fn


import pytest

from xstate import Machine, assign, interpret
from xstate.exceptions import InvalidConfigError
from xstate.scheduler import Clock
from xstate.scxml import _eval_scxml_cond


class ThreadedManualClock(Clock):
    def __init__(self) -> None:
        self._callbacks: dict[int, Callable[[], object]] = {}
        self._next_id = 0
        self._lock = threading.Lock()

    @override
    def set_timeout(self, fn: Callable[[], object], delay_ms: float) -> int:
        with self._lock:
            timeout_id = self._next_id
            self._next_id += 1
            self._callbacks[timeout_id] = fn
            return timeout_id

    @override
    def clear_timeout(self, timeout_id: int) -> None:
        with self._lock:
            self._callbacks.pop(timeout_id, None)

    def fire_all_in_threads(self) -> None:
        with self._lock:
            callbacks = list(self._callbacks.values())
            self._callbacks.clear()
        threads = [threading.Thread(target=callback) for callback in callbacks]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=1)
            assert not thread.is_alive()


def test_sync_interpreter_serializes_concurrent_sends():
    machine = Machine(
        {
            "id": "counter",
            "context": {"count": 0},
            "initial": "active",
            "states": {
                "active": {
                    "on": {
                        "INC": {
                            "actions": [
                                assign({"count": lambda ctx, _ev: ctx["count"] + 1})
                            ]
                        }
                    }
                }
            },
        }
    )
    service = interpret(machine).start()

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(service.send, "INC") for _ in range(100)]
        for future in futures:
            future.result(timeout=1)

    assert service.state.context["count"] == 100


def test_threaded_timer_send_racing_user_send_is_serialized():
    clock = ThreadedManualClock()
    machine = Machine(
        {
            "id": "race",
            "context": {"count": 0},
            "initial": "active",
            "states": {
                "active": {
                    "after": {
                        1: {
                            "actions": [assign({"count": lambda c, _e: c["count"] + 1})]
                        }
                    },
                    "on": {
                        "USER": {
                            "actions": [assign({"count": lambda c, _e: c["count"] + 1})]
                        }
                    },
                }
            },
        }
    )
    service = interpret(machine, clock=clock).start()

    user_thread = threading.Thread(target=service.send, args=("USER",))
    user_thread.start()
    clock.fire_all_in_threads()
    user_thread.join(timeout=1)

    assert not user_thread.is_alive()
    assert service.state.context["count"] == 2


def test_sync_interpreter_clears_queued_events_after_action_error():
    service = None

    def queue_then_boom():
        assert service is not None
        service.send("NEXT")
        raise RuntimeError("boom")

    machine = Machine(
        {
            "id": "clear-queue",
            "context": {"count": 0},
            "initial": "active",
            "states": {
                "active": {
                    "on": {
                        "GO": {"actions": [queue_then_boom]},
                        "NEXT": {
                            "actions": [assign({"count": lambda c, _e: c["count"] + 1})]
                        },
                        "PING": {},
                    }
                }
            },
        }
    )
    service = interpret(machine).start()

    with pytest.raises(RuntimeError, match="boom"):
        service.send("GO")

    service.send("PING")

    assert service.state.context["count"] == 0


def test_sync_interpreter_does_not_hold_lock_while_running_actions():
    service = None

    def send_from_worker_thread():
        assert service is not None
        completed = threading.Event()

        def worker():
            service.send("WORK")
            completed.set()

        thread = threading.Thread(target=worker)
        thread.start()
        assert completed.wait(timeout=1)
        thread.join(timeout=1)
        assert not thread.is_alive()

    machine = Machine(
        {
            "id": "action-lock",
            "context": {"count": 0},
            "initial": "active",
            "states": {
                "active": {
                    "on": {
                        "GO": {"actions": [send_from_worker_thread]},
                        "WORK": {
                            "actions": [assign({"count": lambda c, _e: c["count"] + 1})]
                        },
                    }
                }
            },
        }
    )
    service = interpret(machine).start()

    service.send("GO")

    assert service.state.context["count"] == 1


def test_scxml_boolean_cond_subset():
    assert _eval_scxml_cond("true && !(false || false)")() is True
    assert _eval_scxml_cond("false || (true && false)")() is False


def test_scxml_cond_rejects_unsupported_javascript():
    with pytest.raises(InvalidConfigError, match="Unsupported SCXML JavaScript cond"):
        _eval_scxml_cond("event.name === 'GO'")


def test_state_snapshot_collections_are_immutable():
    machine = Machine({"id": "snap", "initial": "a", "states": {"a": {}}})
    state = machine.initial_state

    assert isinstance(state.configuration, frozenset)
    assert isinstance(state.actions, tuple)
    assert isinstance(state.history_value, MappingProxyType)

    with pytest.raises(AttributeError):
        state.configuration.add(next(iter(state.configuration)))
    with pytest.raises(AttributeError):
        state.actions.append("sentinel")
    with pytest.raises(TypeError):
        state.history_value["x"] = frozenset()

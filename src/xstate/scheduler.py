"""Clock abstractions for delayed (`after`) transitions.

The interpreter schedules delayed events through a :class:`Clock`.  Two
implementations are provided:

* :class:`SimulatedClock` - deterministic, time only advances when the test
  calls :meth:`SimulatedClock.increment`.  This is the recommended clock for
  tests and mirrors XState's ``SimulatedClock``.
* :class:`ThreadClock` - real wall-clock time backed by one on-demand scheduler
  thread, used by the interpreter by default for production use.
"""

from __future__ import annotations

import abc
import heapq
import threading
import time
import traceback
from collections.abc import Callable
from typing import Any, TypedDict, override

__all__ = ["Clock", "SimulatedClock", "ThreadClock"]


class _SimulatedTimeout(TypedDict):
    due: float
    fn: Callable[[], Any]


class Clock(abc.ABC):
    """Interface the interpreter uses to schedule and cancel delayed events."""

    @abc.abstractmethod
    def set_timeout(self, fn: Callable[[], Any], delay_ms: float) -> int:
        """Schedule ``fn`` to run after ``delay_ms`` milliseconds; return a timer id."""

    @abc.abstractmethod
    def clear_timeout(self, timeout_id: int) -> None:
        """Cancel the timer with the given id."""


class SimulatedClock(Clock):
    """Deterministic clock for tests; time advances only via :meth:`increment`."""

    def __init__(self) -> None:
        self._now: float = 0.0
        self._next_id: int = 0
        # timeout_id -> {"due": float, "fn": Callable}
        self._timeouts: dict[int, _SimulatedTimeout] = {}

    @override
    def set_timeout(self, fn: Callable[[], Any], delay_ms: float) -> int:
        timeout_id = self._next_id
        self._next_id += 1
        self._timeouts[timeout_id] = {"due": self._now + delay_ms, "fn": fn}
        return timeout_id

    @override
    def clear_timeout(self, timeout_id: int) -> None:
        self._timeouts.pop(timeout_id, None)

    def now(self) -> float:
        return self._now

    def increment(self, ms: float) -> None:
        """Advance time by ``ms`` and fire every timeout that comes due, in order.

        Timeouts scheduled by callbacks fired during this increment are honored
        if they too come due before ``target``, matching real event-loop ordering.
        """
        target = self._now + ms
        while True:
            due = [(tid, t) for tid, t in self._timeouts.items() if t["due"] <= target]
            if not due:
                break
            # Fire the earliest-due timeout first; ties break by insertion order.
            tid, t = min(due, key=lambda kv: (kv[1]["due"], kv[0]))
            self._now = t["due"]
            del self._timeouts[tid]
            t["fn"]()
        self._now = target


class ThreadClock(Clock):
    """Real-time clock backed by one on-demand scheduler thread."""

    def __init__(self) -> None:
        self._timers: dict[int, tuple[float, Callable[[], Any]]] = {}
        self._heap: list[tuple[float, int]] = []
        self._next_id: int = 0
        self._condition = threading.Condition()
        self._worker: threading.Thread | None = None

    @override
    def set_timeout(self, fn: Callable[[], Any], delay_ms: float) -> int:
        due = time.monotonic() + max(delay_ms, 0.0) / 1000.0
        with self._condition:
            timeout_id = self._next_id
            self._next_id += 1
            self._timers[timeout_id] = (due, fn)
            heapq.heappush(self._heap, (due, timeout_id))
            if self._worker is None:
                self._worker = threading.Thread(
                    target=self._run,
                    name="xstate-thread-clock",
                    daemon=True,
                )
                self._worker.start()
            self._condition.notify()
        return timeout_id

    @override
    def clear_timeout(self, timeout_id: int) -> None:
        with self._condition:
            self._timers.pop(timeout_id, None)
            self._condition.notify()

    def _run(self) -> None:
        while True:
            callback: Callable[[], Any] | None = None
            with self._condition:
                while self._heap:
                    due, timeout_id = self._heap[0]
                    timer = self._timers.get(timeout_id)
                    if timer is None or timer[0] != due:
                        heapq.heappop(self._heap)
                        continue
                    remaining = due - time.monotonic()
                    if remaining > 0:
                        self._condition.wait(timeout=remaining)
                        continue
                    heapq.heappop(self._heap)
                    _due, callback = self._timers.pop(timeout_id)
                    break
                if callback is None:
                    self._worker = None
                    return
            try:
                callback()
            except BaseException:  # noqa: BLE001 - match Timer traceback behavior
                traceback.print_exc()

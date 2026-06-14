"""Clock abstractions for delayed (`after`) transitions.

The interpreter schedules delayed events through a :class:`Clock`.  Two
implementations are provided:

* :class:`SimulatedClock` — deterministic, time only advances when the test
  calls :meth:`SimulatedClock.increment`.  This is the recommended clock for
  tests and mirrors XState's ``SimulatedClock``.
* :class:`ThreadClock` — real wall-clock time backed by ``threading.Timer``,
  used by the interpreter by default for production use.
"""

from __future__ import annotations

import threading
from typing import Callable, Dict


class Clock:
    """Interface the interpreter uses to schedule and cancel delayed events."""

    def set_timeout(self, fn: Callable[[], None], delay_ms: float) -> int:
        raise NotImplementedError

    def clear_timeout(self, timeout_id: int) -> None:
        raise NotImplementedError


class SimulatedClock(Clock):
    """Deterministic clock for tests; time advances only via :meth:`increment`."""

    def __init__(self) -> None:
        self._now: float = 0.0
        self._next_id: int = 0
        # timeout_id -> {"due": float, "fn": Callable}
        self._timeouts: Dict[int, dict] = {}

    def set_timeout(self, fn: Callable[[], None], delay_ms: float) -> int:
        timeout_id = self._next_id
        self._next_id += 1
        self._timeouts[timeout_id] = {"due": self._now + delay_ms, "fn": fn}
        return timeout_id

    def clear_timeout(self, timeout_id: int) -> None:
        self._timeouts.pop(timeout_id, None)

    def now(self) -> float:
        return self._now

    def increment(self, ms: float) -> None:
        """Advance time by ``ms`` and fire every timeout that comes due, in order.

        Timeouts scheduled by callbacks fired during this increment are honoured
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
    """Real-time clock backed by ``threading.Timer`` (interpreter default)."""

    def __init__(self) -> None:
        self._timers: Dict[int, threading.Timer] = {}
        self._next_id: int = 0
        self._lock = threading.Lock()

    def set_timeout(self, fn: Callable[[], None], delay_ms: float) -> int:
        with self._lock:
            timeout_id = self._next_id
            self._next_id += 1
        timer = threading.Timer(delay_ms / 1000.0, fn)
        timer.daemon = True
        self._timers[timeout_id] = timer
        timer.start()
        return timeout_id

    def clear_timeout(self, timeout_id: int) -> None:
        timer = self._timers.pop(timeout_id, None)
        if timer is not None:
            timer.cancel()

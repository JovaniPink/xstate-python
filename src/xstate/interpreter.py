"""Synchronous interpreter for running a :class:`~xstate.machine.Machine`.

The :class:`Machine` API is pure: ``machine.transition(state, event)`` returns a
new :class:`~xstate.state.State` without side effects.  The :class:`Interpreter`
adds the missing runtime pieces that 0.3.0 targets:

* a **running instance** that holds the current state,
* an **event queue** with run-to-completion semantics (events sent while an
  event is already being processed are queued, not interleaved),
* **subscriptions** — listeners notified on every state change,
* **delayed transitions** (`after`) scheduled through a pluggable
  :class:`~xstate.scheduler.Clock`, and cancelled when their state is exited.

Example::

    from xstate import Machine, interpret
    from xstate.scheduler import SimulatedClock

    clock = SimulatedClock()
    service = interpret(machine, clock=clock).start()
    service.send("LOGIN")
    clock.increment(1000)        # fire any `after: {1000: ...}` transitions
    service.state.value
"""

from __future__ import annotations

import functools
import threading
from collections import deque
from collections.abc import Callable
from typing import Any

from xstate.action import CANCEL_TYPE, SEND_PARENT_TYPE, SEND_TO_TYPE, SEND_TYPE, Action
from xstate.event import Event as _Event
from xstate.exceptions import UnregisteredImplementationError
from xstate.machine import Machine
from xstate.scheduler import Clock, ThreadClock
from xstate.state import State

__all__ = [
    "NOT_STARTED",
    "RUNNING",
    "STOPPED",
    "Subscription",
    "Interpreter",
    "interpret",
]

# Interpreter lifecycle states.
NOT_STARTED = "not_started"
RUNNING = "running"
STOPPED = "stopped"


def resolve_delay_ms(
    machine: Machine, delay_spec: Any, context: Any, event: Any
) -> float:
    """Resolve a delay key to milliseconds.

    Numbers are taken as-is; strings are looked up in ``machine.delays`` and may
    be a number or a ``(context, event) -> number`` callable. Shared by the
    synchronous :class:`Interpreter` and the asyncio
    :class:`~xstate.async_interpreter.AsyncInterpreter`.
    """
    if isinstance(delay_spec, (int, float)):
        return float(delay_spec)
    delay = machine.delays.get(delay_spec)
    if delay is None:
        raise UnregisteredImplementationError(
            f"Delay '{delay_spec}' is not configured. "
            f"Pass it via Machine(config, delays={{'{delay_spec}': ...}})."
        )
    if callable(delay):
        from xstate.algorithm import _invoke

        return float(_invoke(delay, context, event))
    return float(delay)


class Subscription:
    """Handle returned by :meth:`Interpreter.subscribe`; call ``unsubscribe``."""

    def __init__(self, interpreter: Interpreter, listener: Callable[[State], None]):
        self._interpreter = interpreter
        self._listener: Callable[[State], None] | None = listener

    def unsubscribe(self) -> None:
        with self._interpreter._lock:
            if self._listener is not None:
                self._interpreter._listeners.discard(self._listener)
                self._listener = None


class Interpreter:
    machine: Machine
    state: State
    clock: Clock

    def __init__(self, machine: Machine, clock: Clock | None = None):
        self.machine = machine
        self.clock = clock if clock is not None else ThreadClock()
        self.state = machine.initial_state
        self._status = NOT_STARTED
        self._lock = threading.RLock()
        self._listeners: set[Callable[[State], None]] = set()
        self._event_queue: deque[Any] = deque()
        self._processing = False
        # `after`-event name → clock timeout id
        self._scheduled: dict[str, int] = {}
        # named `send(..., id=...)` or tid → clock timeout id (all delayed sends)
        self._send_timers: dict[Any, int] = {}
        # Optional back-reference to the owning Actor, set by the actor layer so
        # interpreter-owned actions (send_parent / send_to) can reach the system.
        self._actor: Any | None = None

    # -- lifecycle ----------------------------------------------------------

    @property
    def status(self) -> str:
        return self._status

    @property
    def initialized(self) -> bool:
        return self._status == RUNNING

    def start(self, initial_state: State | None = None) -> Interpreter:
        """Start the service.  Idempotent while already running."""
        with self._lock:
            if self._status == RUNNING:
                return self
            if initial_state is not None:
                self.state = initial_state
            self.state.event = _Event("xstate.init")
            self._status = RUNNING
            self._sync_delays()
            state = self.state
        self._execute(state)
        self._notify(state)
        return self

    def stop(self) -> Interpreter:
        """Stop the service: cancel pending timers and drop all listeners."""
        with self._lock:
            for timeout_id in self._scheduled.values():
                self.clock.clear_timeout(timeout_id)
            self._scheduled.clear()
            for timeout_id in self._send_timers.values():
                self.clock.clear_timeout(timeout_id)
            self._send_timers.clear()
            self._listeners.clear()
            self._event_queue.clear()
            self._status = STOPPED
            return self

    # -- events -------------------------------------------------------------

    def send(self, event: Any) -> State:
        """Send an event.  Events sent during processing are queued (RTC)."""
        with self._lock:
            if self._status != RUNNING:
                # Match XState: events before start / after stop are dropped.
                return self.state

            self._event_queue.append(event)
            if self._processing:
                return self.state

            self._processing = True
        self._drain_event_queue()
        with self._lock:
            return self.state

    def _drain_event_queue(self) -> None:
        while True:
            with self._lock:
                if self._status != RUNNING or not self._event_queue:
                    self._processing = False
                    return
                next_event = self._event_queue.popleft()
            try:
                self._process(next_event)
            except Exception:
                with self._lock:
                    self._event_queue.clear()
                    self._processing = False
                raise

    def _process(self, event: Any) -> None:
        with self._lock:
            if self._status != RUNNING:
                return
            state = self.state

        next_state = self.machine.transition(state, event)
        next_state.event = self.machine._to_event(event)

        with self._lock:
            if self._status != RUNNING:
                return
            self.state = next_state
            self._sync_delays()

        self._execute(next_state)
        self._notify(next_state)

    # -- subscriptions ------------------------------------------------------

    def subscribe(self, listener: Callable[[State], None]) -> Subscription:
        """Register a listener called with the current state and on each change."""
        with self._lock:
            self._listeners.add(listener)
            state = self.state if self._status == RUNNING else None
        if state is not None:
            listener(state)
        return Subscription(self, listener)

    def _notify(self, state: State) -> None:
        with self._lock:
            listeners = tuple(self._listeners)
        for listener in listeners:
            listener(state)

    # -- side effects -------------------------------------------------------

    _ACTION_DISPATCH: dict[str, str] = {
        SEND_TYPE: "_execute_send",
        CANCEL_TYPE: "_execute_cancel",
        SEND_PARENT_TYPE: "_execute_send_parent",
        SEND_TO_TYPE: "_execute_send_to",
    }

    def _execute(self, state: State) -> None:
        """Run resolved action callables and handle interpreter-owned actions."""
        for action in state.actions:
            if isinstance(action, Action):
                action_type = action.type
                method_name = (
                    self._ACTION_DISPATCH.get(action_type)
                    if isinstance(action_type, str)
                    else None
                )
                if method_name:
                    getattr(self, method_name)(action)
            elif callable(action):
                action()

    def _execute_send(self, action: Action) -> None:
        event = action.data.get("event")
        delay = action.data.get("delay")
        send_id = action.data.get("id")
        if delay is not None:
            delay_ms = self._resolve_delay(delay)
            tid = self.clock.set_timeout(functools.partial(self.send, event), delay_ms)
            # Use the explicit id if given; fall back to tid so stop() can
            # cancel anonymous delayed sends too.
            self._send_timers[send_id if send_id else tid] = tid
        else:
            self.send(event)

    def _execute_cancel(self, action: Action) -> None:
        send_id = action.data.get("sendid")
        if send_id:
            tid = self._send_timers.pop(send_id, None)
            if tid is not None:
                self.clock.clear_timeout(tid)

    def _execute_send_parent(self, action: Action) -> None:
        """Route a ``send_parent`` action to the owning actor's parent."""
        if self._actor is None or self._actor.parent is None:
            return
        self._deliver_external(self._actor.parent, action)

    def _execute_send_to(self, action: Action) -> None:
        """Route a ``send_to`` action to a sibling actor by id."""
        if self._actor is None:
            return
        target = self._actor.system.get(action.data.get("target"))
        if target is None:
            return
        self._deliver_external(target, action)

    def _deliver_external(self, target: Any, action: Action) -> None:
        """Deliver an event to another actor, immediately or after a delay."""
        event = action.data.get("event")
        delay = action.data.get("delay")
        send_id = action.data.get("id")
        if delay is not None:
            delay_ms = self._resolve_delay(delay)
            tid = self.clock.set_timeout(
                functools.partial(target.send, event), delay_ms
            )
            self._send_timers[send_id if send_id else tid] = tid
        else:
            target.send(event)

    # -- delayed transitions ------------------------------------------------

    def _resolve_delay(self, delay_spec: Any) -> float:
        return resolve_delay_ms(
            self.machine,
            delay_spec,
            self.state.context,
            getattr(self.state, "event", None),
        )

    def _sync_delays(self) -> None:
        """Reconcile scheduled timers with the current configuration.

        Timers for states still active are left running; timers for exited
        states are cancelled; newly entered states with `after` are scheduled.
        """
        wanted: dict[str, object] = {}
        for node in self.state.configuration:
            for delay_spec, event_name in getattr(node, "after", []):
                wanted[event_name] = delay_spec

        # Cancel timers whose state is no longer active.
        for event_name in list(self._scheduled):
            if event_name not in wanted:
                self.clock.clear_timeout(self._scheduled.pop(event_name))

        # Schedule timers for newly entered delayed transitions.
        for event_name, delay_spec in wanted.items():
            if event_name in self._scheduled:
                continue
            delay_ms = self._resolve_delay(delay_spec)
            # Bind event_name per-iteration so each timer sends its own event.
            self._scheduled[event_name] = self.clock.set_timeout(
                functools.partial(self.send, event_name), delay_ms
            )


def interpret(machine: Machine, clock: Clock | None = None) -> Interpreter:
    """Create an :class:`Interpreter` for ``machine`` (XState ``interpret``)."""
    return Interpreter(machine, clock=clock)

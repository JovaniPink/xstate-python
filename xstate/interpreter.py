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

from typing import Any, Callable, Dict, List, Optional

from xstate.action import CANCEL_TYPE, SEND_PARENT_TYPE, SEND_TO_TYPE, SEND_TYPE, Action
from xstate.event import Event as _Event
from xstate.machine import Machine
from xstate.scheduler import Clock, ThreadClock
from xstate.state import State

# Interpreter lifecycle states.
NOT_STARTED = "not_started"
RUNNING = "running"
STOPPED = "stopped"


class Subscription:
    """Handle returned by :meth:`Interpreter.subscribe`; call ``unsubscribe``."""

    def __init__(self, interpreter: "Interpreter", listener: Callable[[State], None]):
        self._interpreter = interpreter
        self._listener: Optional[Callable[[State], None]] = listener

    def unsubscribe(self) -> None:
        if self._listener is not None:
            self._interpreter._listeners.discard(self._listener)
            self._listener = None


class Interpreter:
    machine: Machine
    state: State
    clock: Clock

    def __init__(self, machine: Machine, clock: Optional[Clock] = None):
        self.machine = machine
        self.clock = clock if clock is not None else ThreadClock()
        self.state = machine.initial_state
        self._status = NOT_STARTED
        self._listeners: set = set()
        self._event_queue: List = []
        self._processing = False
        # `after`-event name → clock timeout id
        self._scheduled: Dict[str, int] = {}
        # named `send(..., id=...)` or tid → clock timeout id (all delayed sends)
        self._send_timers: Dict = {}
        # Optional back-reference to the owning Actor, set by the actor layer so
        # interpreter-owned actions (send_parent / send_to) can reach the system.
        self._actor: Optional[Any] = None

    # -- lifecycle ----------------------------------------------------------

    @property
    def status(self) -> str:
        return self._status

    @property
    def initialized(self) -> bool:
        return self._status == RUNNING

    def start(self, initial_state: Optional[State] = None) -> "Interpreter":
        """Start the service.  Idempotent while already running."""
        if self._status == RUNNING:
            return self
        if initial_state is not None:
            self.state = initial_state
        self.state.event = _Event("xstate.init")
        self._status = RUNNING
        self._sync_delays()
        self._execute(self.state)
        self._notify(self.state)
        return self

    def stop(self) -> "Interpreter":
        """Stop the service: cancel pending timers and drop all listeners."""
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

    def send(self, event) -> State:
        """Send an event.  Events sent during processing are queued (RTC)."""
        if self._status != RUNNING:
            # Match XState: events before start / after stop are dropped.
            return self.state

        self._event_queue.append(event)
        if self._processing:
            return self.state

        self._processing = True
        try:
            while self._event_queue:
                next_event = self._event_queue.pop(0)
                self._process(next_event)
        finally:
            self._processing = False
        return self.state

    def _process(self, event) -> None:
        next_state = self.machine.transition(self.state, event)
        next_state.event = self.machine._to_event(event)
        self.state = next_state
        self._sync_delays()
        self._execute(next_state)
        self._notify(next_state)

    # -- subscriptions ------------------------------------------------------

    def subscribe(self, listener: Callable[[State], None]) -> Subscription:
        """Register a listener called with the current state and on each change."""
        self._listeners.add(listener)
        if self._status == RUNNING:
            listener(self.state)
        return Subscription(self, listener)

    def _notify(self, state: State) -> None:
        for listener in list(self._listeners):
            listener(state)

    # -- side effects -------------------------------------------------------

    _ACTION_DISPATCH: Dict[str, str] = {
        SEND_TYPE: "_execute_send",
        CANCEL_TYPE: "_execute_cancel",
        SEND_PARENT_TYPE: "_execute_send_parent",
        SEND_TO_TYPE: "_execute_send_to",
    }

    def _execute(self, state: State) -> None:
        """Run resolved action callables and handle interpreter-owned actions."""
        for action in state.actions:
            if isinstance(action, Action):
                method_name = self._ACTION_DISPATCH.get(action.type)
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
            tid = self.clock.set_timeout(
                (lambda e: lambda: self.send(e))(event), delay_ms
            )
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

    def _deliver_external(self, target, action: Action) -> None:
        """Deliver an event to another actor, immediately or after a delay."""
        event = action.data.get("event")
        delay = action.data.get("delay")
        send_id = action.data.get("id")
        if delay is not None:
            delay_ms = self._resolve_delay(delay)
            tid = self.clock.set_timeout(
                (lambda t, e: lambda: t.send(e))(target, event), delay_ms
            )
            self._send_timers[send_id if send_id else tid] = tid
        else:
            target.send(event)

    # -- delayed transitions ------------------------------------------------

    def _resolve_delay(self, delay_spec) -> float:
        """Resolve a delay key to milliseconds.

        Numbers are taken as-is; strings are looked up in ``machine.delays`` and
        may be a number or a ``(context, event) -> number`` callable.
        """
        if isinstance(delay_spec, (int, float)):
            return float(delay_spec)
        delay = self.machine.delays.get(delay_spec)
        if delay is None:
            raise ValueError(
                f"Delay '{delay_spec}' is not configured. "
                f"Pass it via Machine(config, delays={{'{delay_spec}': ...}})."
            )
        if callable(delay):
            from xstate.algorithm import _invoke

            return float(
                _invoke(delay, self.state.context, getattr(self.state, "event", None))
            )
        return float(delay)

    def _sync_delays(self) -> None:
        """Reconcile scheduled timers with the current configuration.

        Timers for states still active are left running; timers for exited
        states are cancelled; newly entered states with `after` are scheduled.
        """
        wanted: Dict[str, object] = {}
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
                (lambda en: lambda: self.send(en))(event_name), delay_ms
            )


def interpret(machine: Machine, clock: Optional[Clock] = None) -> Interpreter:
    """Create an :class:`Interpreter` for ``machine`` (XState ``interpret``)."""
    return Interpreter(machine, clock=clock)

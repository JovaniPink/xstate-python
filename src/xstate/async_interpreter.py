"""Asyncio-native interpreter for running a :class:`~xstate.machine.Machine`.

:class:`AsyncInterpreter` is the ``asyncio`` counterpart of the synchronous
:class:`~xstate.interpreter.Interpreter`.  It targets the 0.5.0 async milestone:
running a statechart inside an event loop so it composes with async Python
(FastAPI, async Django, aiohttp, Celery's async worker, …).

What is and isn't async
-----------------------
The *pure* transition computation stays synchronous: ``machine.transition`` is a
side-effect-free function from ``(state, event)`` to a new state, and guards /
assigners run inside it.  The async layer wraps only the **runtime**:

* ``await start()`` / ``await send(event)`` / ``await stop()``;
* a run-to-completion event queue (events sent while one is being processed are
  queued, never interleaved);
* **awaitable action callables** — an action that returns a coroutine is
  awaited, so ``async def`` side effects work transparently;
* **delayed transitions** (`after`) scheduled on the running event loop via
  :func:`asyncio.create_task` and cancelled when their state is exited or the
  service stops.

This boundary mirrors XState, which keeps logic pure and pushes effects to the
actor/runtime edge.  Keeping guards synchronous means the SCXML algorithm core
is shared unchanged between the sync and async runtimes.

Example::

    import asyncio
    from xstate import Machine, interpret_async

    async def main():
        service = await interpret_async(machine).start()
        await service.send("LOGIN")
        print(service.state.value)
        await service.stop()

    asyncio.run(main())
"""

from __future__ import annotations

import asyncio
import inspect
from collections import deque
from collections.abc import Callable
from typing import Any

from xstate.action import CANCEL_TYPE, SEND_TYPE, Action
from xstate.event import Event as _Event
from xstate.interpreter import NOT_STARTED, RUNNING, STOPPED, resolve_delay_ms
from xstate.machine import Machine
from xstate.state import State

__all__ = ["AsyncSubscription", "AsyncInterpreter", "interpret_async"]

_QueuedEvent = tuple[Any, "asyncio.Future[State]"]


class AsyncSubscription:
    """Handle returned by :meth:`AsyncInterpreter.subscribe`; call ``unsubscribe``."""

    def __init__(
        self, interpreter: AsyncInterpreter, listener: Callable[[State], None]
    ):
        self._interpreter = interpreter
        self._listener: Callable[[State], None] | None = listener

    def unsubscribe(self) -> None:
        if self._listener is not None:
            self._interpreter._listeners.discard(self._listener)
            self._listener = None


class AsyncInterpreter:
    """An asyncio-native running instance of a :class:`~xstate.machine.Machine`.

    Lifecycle and messaging are coroutines (``start`` / ``send`` / ``stop``);
    observation (``subscribe``) and the current ``state`` are synchronous, since
    snapshots are plain values.  Delayed transitions are scheduled on whichever
    loop is running when the service is started.
    """

    machine: Machine
    state: State

    def __init__(self, machine: Machine):
        self.machine = machine
        self.state = machine.initial_state
        self._status = NOT_STARTED
        self._listeners: set[Callable[[State], None]] = set()
        self._event_queue: deque[_QueuedEvent] = deque()
        self._processing = False
        self._processing_task: asyncio.Task[Any] | None = None
        # `after`-event name -> asyncio.Task running the delay
        self._scheduled: dict[str, asyncio.Task] = {}
        # named `send(..., id=...)` (or the Task itself) -> delayed-send Task
        self._send_timers: dict[Any, asyncio.Task] = {}

    # -- lifecycle ----------------------------------------------------------

    @property
    def status(self) -> str:
        return self._status

    @property
    def initialized(self) -> bool:
        return self._status == RUNNING

    async def start(self, initial_state: State | None = None) -> AsyncInterpreter:
        """Start the service. Idempotent while already running."""
        if self._status == RUNNING:
            return self
        if initial_state is not None:
            self.state = initial_state
        self.state.event = _Event("xstate.init")
        self._status = RUNNING
        self._sync_delays()
        await self._execute(self.state)
        self._notify(self.state)
        return self

    async def stop(self) -> AsyncInterpreter:
        """Stop the service: cancel pending timers and drop all listeners."""
        for task in self._scheduled.values():
            task.cancel()
        self._scheduled.clear()
        for task in self._send_timers.values():
            task.cancel()
        self._send_timers.clear()
        self._listeners.clear()
        self._resolve_queued_events(self.state)
        self._status = STOPPED
        return self

    # -- events -------------------------------------------------------------

    async def send(self, event: Any) -> State:
        """Send an event. Events sent during processing are queued (RTC)."""
        if self._status != RUNNING:
            # Match XState: events before start / after stop are dropped.
            return self.state

        future: asyncio.Future[State] = asyncio.get_running_loop().create_future()
        self._event_queue.append((event, future))
        if self._processing:
            # Same-task re-entrant sends from an action must not await their own
            # queued future: the active drain cannot process that future until
            # the action returns.
            if asyncio.current_task() is self._processing_task:
                return self.state
            return await future

        self._processing = True
        self._processing_task = asyncio.current_task()
        try:
            while self._event_queue:
                next_event, event_done = self._event_queue.popleft()
                try:
                    await self._process(next_event)
                except Exception as exc:
                    if not event_done.done():
                        event_done.set_exception(exc)
                        event_done.exception()
                    self._fail_queued_events(exc)
                    raise
                if not event_done.done():
                    event_done.set_result(self.state)
        finally:
            self._processing = False
            self._processing_task = None
        return future.result()

    def _resolve_queued_events(self, state: State) -> None:
        while self._event_queue:
            _event, future = self._event_queue.popleft()
            if not future.done():
                future.set_result(state)

    def _fail_queued_events(self, exc: BaseException) -> None:
        while self._event_queue:
            _event, future = self._event_queue.popleft()
            if not future.done():
                future.set_exception(exc)
                future.exception()

    async def _process(self, event: Any) -> None:
        next_state = self.machine.transition(self.state, event)
        next_state.event = self.machine._to_event(event)
        self.state = next_state
        self._sync_delays()
        await self._execute(next_state)
        self._notify(next_state)

    # -- subscriptions ------------------------------------------------------

    def subscribe(self, listener: Callable[[State], None]) -> AsyncSubscription:
        """Register a listener called with the current state and on each change.

        Listeners are synchronous observers (as in XState); perform async work
        inside actions, not subscribers.
        """
        self._listeners.add(listener)
        if self._status == RUNNING:
            listener(self.state)
        return AsyncSubscription(self, listener)

    def _notify(self, state: State) -> None:
        for listener in list(self._listeners):
            listener(state)

    # -- side effects -------------------------------------------------------

    _ACTION_DISPATCH: dict[str, str] = {
        SEND_TYPE: "_execute_send",
        CANCEL_TYPE: "_execute_cancel",
    }

    async def _execute(self, state: State) -> None:
        """Run resolved action callables; await any that return a coroutine."""
        for action in state.actions:
            if isinstance(action, Action):
                action_type = action.type
                method_name = (
                    self._ACTION_DISPATCH.get(action_type)
                    if isinstance(action_type, str)
                    else None
                )
                if method_name:
                    await getattr(self, method_name)(action)
            elif callable(action):
                result = action()
                if inspect.isawaitable(result):
                    await result

    async def _execute_send(self, action: Action) -> None:
        event = action.data.get("event")
        delay = action.data.get("delay")
        send_id = action.data.get("id")
        if delay is not None:
            delay_ms = resolve_delay_ms(
                self.machine, delay, self.state.context, self.state.event
            )
            task = self._schedule(self.send, event, delay_ms)
            # Key by explicit id when given so cancel() can find it; otherwise key
            # by the Task itself so stop() can still cancel anonymous sends.
            self._send_timers[send_id if send_id else task] = task
        else:
            await self.send(event)

    async def _execute_cancel(self, action: Action) -> None:
        send_id = action.data.get("sendid")
        if send_id:
            task = self._send_timers.pop(send_id, None)
            if task is not None:
                task.cancel()

    # -- delayed transitions ------------------------------------------------

    def _schedule(
        self, coro_fn: Callable[[Any], Any], arg: Any, delay_ms: float
    ) -> asyncio.Task:
        """Create a task that waits ``delay_ms`` then calls ``coro_fn(arg)``."""

        async def _fire() -> None:
            try:
                await asyncio.sleep(delay_ms / 1000)
            except asyncio.CancelledError:
                return
            if self._status == RUNNING:
                await coro_fn(arg)

        return asyncio.create_task(_fire())

    def _sync_delays(self) -> None:
        """Reconcile scheduled `after` timers with the current configuration.

        Timers for states still active are left running; timers for exited
        states are cancelled; newly entered states with `after` are scheduled.
        Each delay fires once per entry (a still-active state is not rescheduled).
        """
        wanted: dict[str, object] = {}
        for node in self.state.configuration:
            for delay_spec, event_name in getattr(node, "after", []):
                wanted[event_name] = delay_spec

        # Cancel timers whose state is no longer active.
        for event_name in list(self._scheduled):
            if event_name not in wanted:
                self._scheduled.pop(event_name).cancel()

        # Schedule timers for newly entered delayed transitions.
        for event_name, delay_spec in wanted.items():
            if event_name in self._scheduled:
                continue
            delay_ms = resolve_delay_ms(
                self.machine, delay_spec, self.state.context, self.state.event
            )
            self._scheduled[event_name] = self._schedule(
                self.send, event_name, delay_ms
            )


def interpret_async(machine: Machine) -> AsyncInterpreter:
    """Create an :class:`AsyncInterpreter` for ``machine``.

    The asyncio counterpart of :func:`~xstate.interpreter.interpret`. The service
    is not started; ``await`` its :meth:`AsyncInterpreter.start`.
    """
    return AsyncInterpreter(machine)

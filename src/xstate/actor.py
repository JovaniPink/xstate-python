"""Actor model (0.5.0).

XState v5 reframes a running machine as an **actor**: a live unit with an
address (``id``), a mailbox (``send``), an observable snapshot, and membership
in an **actor system**.  ``create_actor(logic)`` replaces ``interpret(machine)``
as the v5 entry point.

This module provides:

* :class:`ActorSystem` — a registry that every actor belongs to; actors are
  reachable by id via :meth:`ActorSystem.get`.
* :class:`Actor` — a running instance of *actor logic*.  An actor wraps a
  pluggable backend chosen from the logic it is created with:

  - a :class:`~xstate.machine.Machine` → a state-machine actor backed by the
    existing :class:`~xstate.interpreter.Interpreter`;
  - :func:`from_promise` logic → a promise actor that resolves (or rejects)
    once when started;
  - :func:`from_callback` logic → a callback actor that bridges external event
    sources via ``send_back`` / ``receive``.

* :func:`create_actor` — build an actor from any of those logic kinds.
* The **parent/child actor tree**: :meth:`Actor.spawn` creates a child actor in
  the same system, and ``invoke:`` on a state spawns a child actor for the
  lifetime of that state, feeding its completion back as ``done.invoke.<id>`` /
  ``error.platform.<id>`` events.

Sync and async resolution: the machine layer runs on the synchronous
:class:`~xstate.interpreter.Interpreter`, so a :func:`from_promise` actor with a
*plain* function is called eagerly on ``start`` and resolves immediately.  A
:func:`from_promise` actor with an ``async def`` (coroutine) function, and any
:func:`from_observable` actor, instead schedule their work as an
:class:`asyncio.Task` on the running event loop and resolve / emit later — so
they require a running loop (start them inside ``asyncio.run(...)``).
:func:`to_promise` adapts any actor to an :class:`asyncio.Future` that resolves
with its ``output`` (or raises its ``error``).
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterable, Callable
from typing import Any, Literal, Protocol, cast

from xstate.event import Event
from xstate.interpreter import NOT_STARTED, RUNNING, STOPPED, Interpreter, Subscription
from xstate.machine import Machine
from xstate.scheduler import Clock
from xstate.state import State

__all__ = [
    "PromiseLogic",
    "CallbackLogic",
    "ObservableLogic",
    "ActorSnapshot",
    "ActorSystem",
    "Actor",
    "ActorLogic",
    "ActorSnapshotValue",
    "SubscriptionProtocol",
    "from_promise",
    "from_callback",
    "from_observable",
    "create_actor",
    "to_promise",
]


class SubscriptionProtocol(Protocol):
    def unsubscribe(self) -> None: ...


# ---------------------------------------------------------------------------
# Actor logic kinds
# ---------------------------------------------------------------------------


class PromiseLogic:
    """Logic that runs ``fn(input)`` once and resolves with its return value.

    Created with :func:`from_promise`.  On success the actor snapshot becomes
    ``status == "done"`` with ``output`` set to the return value; if ``fn``
    raises, the snapshot becomes ``status == "error"`` with ``error`` set.
    """

    def __init__(self, fn: Callable[..., Any]):
        self.fn = fn


class CallbackLogic:
    """Logic that bridges an external event source.

    Created with :func:`from_callback`.  On start the actor calls
    ``fn(send_back=..., receive=..., input=...)`` (only the parameters ``fn``
    declares are passed).  ``send_back(event)`` delivers an event to the
    parent actor; ``receive(handler)`` registers a handler for events sent to
    this actor.  If ``fn`` returns a callable it is run as cleanup on stop.
    """

    def __init__(self, fn: Callable[..., Any]):
        self.fn = fn


class ObservableLogic:
    """Logic that emits each value from an async iterable.

    Created with :func:`from_observable`.  On start the actor iterates the
    async iterable returned by ``fn(input)`` (or ``fn`` itself if it is already
    an async iterable) as an :class:`asyncio.Task`: each value updates the
    snapshot (``status == "active"`` with ``context`` set to the value and the
    listeners notified); when the iterable is exhausted the snapshot becomes
    ``status == "done"`` with ``output`` set to the final value, and if it
    raises, ``status == "error"``.
    """

    def __init__(self, fn: Any):
        self.fn = fn


type ActorLogic = Machine | PromiseLogic | CallbackLogic | ObservableLogic


def from_promise(fn: Callable[..., Any]) -> PromiseLogic:
    """Create promise actor logic from ``fn`` (XState v5 ``fromPromise``).

    ``fn`` may be synchronous (resolves eagerly on start) or an ``async def``
    coroutine function (resolved on the running event loop).
    """
    return PromiseLogic(fn)


def from_callback(fn: Callable[..., Any]) -> CallbackLogic:
    """Create callback actor logic from ``fn`` (XState v5 ``fromCallback``)."""
    return CallbackLogic(fn)


def from_observable(
    fn: Callable[..., AsyncIterable[Any]] | AsyncIterable[Any],
) -> ObservableLogic:
    """Create observable actor logic from ``fn`` (XState v5 ``fromObservable``).

    ``fn`` is a callable returning an async iterable (e.g. an async generator
    function), or an async iterable directly.  Requires a running event loop.
    """
    return ObservableLogic(fn)


def _ensure_future(awaitable: Any) -> asyncio.Task:
    """Schedule *awaitable* on the running loop, with a clear error if none.

    Async actor logic (coroutine ``from_promise`` / ``from_observable``) can
    only run when an event loop is active; surface that requirement explicitly
    rather than letting a lower-level ``RuntimeError`` leak.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # Close the orphaned coroutine so it doesn't emit a "never awaited"
        # warning when garbage-collected.
        if inspect.iscoroutine(awaitable):
            awaitable.close()
        raise RuntimeError(
            "Async actor logic (a coroutine from_promise or a from_observable) "
            "requires a running event loop. Start the actor inside an async "
            "context, e.g. within asyncio.run(...)."
        ) from None
    return asyncio.ensure_future(awaitable)


def _call_with_supported_kwargs(fn: Callable[..., Any], **kwargs: Any) -> Any:
    """Call ``fn`` passing only the keyword arguments it declares.

    Lets actor-logic functions opt into ``input`` / ``send_back`` / ``receive``
    by simply naming the parameters they need, ignoring the rest.
    """
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return fn(**kwargs)
    params = sig.parameters
    if any(p.kind == p.VAR_KEYWORD for p in params.values()):
        return fn(**kwargs)
    args = []
    kwargs_to_pass = {}
    for name, param in params.items():
        if name in kwargs:
            if param.kind == inspect.Parameter.POSITIONAL_ONLY:
                args.append(kwargs[name])
            else:
                kwargs_to_pass[name] = kwargs[name]
    return fn(*args, **kwargs_to_pass)


# ---------------------------------------------------------------------------
# Snapshots / subscriptions for non-machine backends
# ---------------------------------------------------------------------------


class ActorSnapshot:
    """Minimal snapshot for promise/callback actors.

    Mirrors the fields a machine :class:`~xstate.state.State` exposes
    (``status`` / ``output`` / ``error``) so consumers can treat every actor's
    snapshot uniformly.
    """

    def __init__(
        self,
        status: Literal["active", "done", "error"],
        output: Any | None = None,
        error: Any | None = None,
        context: Any | None = None,
    ):
        self.status: Literal["active", "done", "error"] = status
        self.output = output
        self.error = error
        self.context = context
        self.value = status

    def __repr__(self) -> str:
        return (
            f"ActorSnapshot(status={self.status!r},"
            f" output={self.output!r}, error={self.error!r})"
        )


class _ListenerSubscription:
    """``unsubscribe``-able handle over a plain listener set."""

    def __init__(
        self,
        listeners: set[Callable[[Any], None]],
        listener: Callable[[Any], None],
    ) -> None:
        self._listeners = listeners
        self._listener: Callable[[Any], None] | None = listener

    def unsubscribe(self) -> None:
        if self._listener is not None:
            self._listeners.discard(self._listener)
            self._listener = None


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


class _ListenerBackend:
    """Shared listener/status/snapshot plumbing for non-machine backends.

    Holds the observer set, the lifecycle ``status``, and the current snapshot,
    and implements ``subscribe`` / ``_notify`` once so :class:`_PromiseBackend`
    and :class:`_CallbackBackend` only define their own ``start`` / ``stop`` /
    ``send`` behaviour.
    """

    is_machine = False

    def __init__(self, actor: Actor, input: Any):
        self._actor = actor
        self._input = input
        self._listeners: set[Callable[[Any], None]] = set()
        self._snapshot = ActorSnapshot("active")
        self._status = NOT_STARTED

    @property
    def status(self) -> str:
        return self._status

    @property
    def snapshot(self) -> ActorSnapshot:
        return self._snapshot

    def subscribe(
        self, listener: Callable[[ActorSnapshot], None]
    ) -> _ListenerSubscription:
        self._listeners.add(listener)
        if self._status == RUNNING:
            listener(self._snapshot)
        return _ListenerSubscription(self._listeners, listener)

    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener(self._snapshot)


class _MachineBackend:
    """Backs an actor with a :class:`~xstate.machine.Machine` via Interpreter."""

    is_machine = True

    def __init__(self, actor: Actor, machine: Machine, clock: Clock | None):
        self.interpreter = Interpreter(machine, clock=clock)
        # Back-reference so interpreter-owned actions (send_parent / send_to)
        # can reach the actor and its system.
        self.interpreter._actor = actor
        # Whether any state declares `invoke:` — lets the actor skip installing
        # the per-change invocation reconciler for invoke-free machines.
        self.has_invoke = any(
            getattr(node, "invoke", None) for node in machine._id_map.values()
        )

    @property
    def status(self) -> str:
        return self.interpreter.status

    @property
    def snapshot(self) -> State:
        return self.interpreter.state

    def start(self, initial_state: State | None = None) -> None:
        self.interpreter.start(initial_state)

    def stop(self) -> None:
        self.interpreter.stop()

    def send(self, event: object) -> Any:
        return self.interpreter.send(event)

    def subscribe(self, listener: Callable[[State], None]) -> Subscription:
        return self.interpreter.subscribe(listener)


class _PromiseBackend(_ListenerBackend):
    """Backs an actor with :func:`from_promise` logic.

    A plain function resolves synchronously on :meth:`start`; a coroutine
    function is scheduled on the event loop and resolves via a done-callback.
    """

    def __init__(self, actor: Actor, logic: PromiseLogic, input: Any):
        super().__init__(actor, input)
        self._fn = logic.fn
        self._task: asyncio.Task | None = None

    def start(self, initial_state: State | None = None) -> None:
        if self._status != NOT_STARTED:
            return
        self._status = RUNNING
        try:
            result = _call_with_supported_kwargs(self._fn, input=self._input)
        except Exception as exc:  # noqa: BLE001 - surfaced as actor error
            self._snapshot = ActorSnapshot("error", error=exc)
            self._notify()
            return
        if inspect.isawaitable(result):
            # Defer resolution to the event loop; snapshot stays "active" until
            # the coroutine completes.
            self._task = _ensure_future(result)
            self._task.add_done_callback(self._on_resolved)
        else:
            self._snapshot = ActorSnapshot("done", output=result)
            self._notify()

    def _on_resolved(self, task: asyncio.Task) -> None:
        if self._status == STOPPED or task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            self._snapshot = ActorSnapshot("error", error=exc)
        else:
            self._snapshot = ActorSnapshot("done", output=task.result())
        self._notify()

    def stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None
        self._status = STOPPED
        self._listeners.clear()

    def send(self, event: object) -> ActorSnapshot:
        # Promise actors ignore incoming events.
        return self._snapshot


class _CallbackBackend(_ListenerBackend):
    """Backs an actor with :func:`from_callback` logic."""

    def __init__(self, actor: Actor, logic: CallbackLogic, input: Any):
        super().__init__(actor, input)
        self._fn = logic.fn
        self._receivers: list[Callable[[Any], None]] = []
        self._cleanup: Callable[[], None] | None = None

    def start(self, initial_state: State | None = None) -> None:
        if self._status != NOT_STARTED:
            return
        self._status = RUNNING

        def send_back(event: object) -> None:
            parent = self._actor.parent
            if parent is not None:
                parent.send(event)

        def receive(handler: Callable[[Any], None]) -> None:
            self._receivers.append(handler)

        self._cleanup = _call_with_supported_kwargs(
            self._fn, send_back=send_back, receive=receive, input=self._input
        )
        self._notify()

    def stop(self) -> None:
        if callable(self._cleanup):
            self._cleanup()
        self._cleanup = None
        self._status = STOPPED
        self._receivers.clear()
        self._listeners.clear()

    def send(self, event: object) -> ActorSnapshot:
        for handler in list(self._receivers):
            handler(event)
        return self._snapshot


class _ObservableBackend(_ListenerBackend):
    """Backs an actor with :func:`from_observable` logic."""

    def __init__(self, actor: Actor, logic: ObservableLogic, input: Any):
        super().__init__(actor, input)
        self._fn = logic.fn
        self._task: asyncio.Task | None = None

    def start(self, initial_state: State | None = None) -> None:
        if self._status != NOT_STARTED:
            return
        self._status = RUNNING
        try:
            source = (
                _call_with_supported_kwargs(self._fn, input=self._input)
                if callable(self._fn)
                else self._fn
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as actor error
            self._snapshot = ActorSnapshot("error", error=exc)
            self._notify()
            return
        self._task = _ensure_future(self._consume(source))
        self._task.add_done_callback(self._on_finished)

    async def _consume(self, source: Any) -> Any:
        last = None
        async for value in source:
            if self._status == STOPPED:
                break
            last = value
            self._snapshot = ActorSnapshot("active", context=value)
            self._notify()
        return last

    def _on_finished(self, task: asyncio.Task) -> None:
        if self._status == STOPPED or task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            self._snapshot = ActorSnapshot("error", error=exc)
        else:
            self._snapshot = ActorSnapshot("done", output=task.result())
        self._notify()

    def stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None
        self._status = STOPPED
        self._listeners.clear()

    def send(self, event: object) -> ActorSnapshot:
        # Observable actors ignore incoming events.
        return self._snapshot


type ActorBackend = (
    _MachineBackend | _PromiseBackend | _CallbackBackend | _ObservableBackend
)
type ActorSnapshotValue = State | ActorSnapshot


def _build_backend(
    actor: Actor, logic: ActorLogic, clock: Clock | None, input: Any
) -> ActorBackend:
    if isinstance(logic, Machine):
        return _MachineBackend(actor, logic, clock)
    if isinstance(logic, PromiseLogic):
        return _PromiseBackend(actor, logic, input)
    if isinstance(logic, CallbackLogic):
        return _CallbackBackend(actor, logic, input)
    if isinstance(logic, ObservableLogic):
        return _ObservableBackend(actor, logic, input)
    raise TypeError(
        "create_actor expects a Machine, from_promise(...), from_callback(...), "
        f"or from_observable(...) logic, got {type(logic).__name__}."
    )


# ---------------------------------------------------------------------------
# Actor system
# ---------------------------------------------------------------------------


class ActorSystem:
    """Registry of actors. Every actor belongs to exactly one system.

    Mirrors XState v5's ``system``: actors can be looked up by id with
    :meth:`get`, which is how one actor addresses another without holding a
    direct reference.
    """

    def __init__(self) -> None:
        self._actors: dict[str, Actor] = {}
        self._anonymous_count = 0

    def _next_id(self) -> str:
        """Generate an id for an actor created without an explicit one.

        Skips ids already taken so an anonymous actor never collides with an
        explicit ``"x:N"`` id a caller chose.
        """
        candidate = f"x:{self._anonymous_count}"
        while candidate in self._actors:
            self._anonymous_count += 1
            candidate = f"x:{self._anonymous_count}"
        self._anonymous_count += 1
        return candidate

    def _register(self, actor: Actor) -> None:
        actor_id = actor.id
        if actor_id in self._actors and self._actors[actor_id] is not actor:
            raise ValueError(
                f"An actor with id '{actor_id}' is already registered in this system."
            )
        self._actors[actor_id] = actor

    def _unregister(self, actor: Actor) -> None:
        actor_id = actor.id
        if self._actors.get(actor_id) is actor:
            del self._actors[actor_id]

    def get(self, actor_id: str) -> Actor | None:
        """Return the actor registered under *actor_id*, or ``None``."""
        return self._actors.get(actor_id)


class Actor:
    """A running instance of actor logic with an address in a system.

    Lifecycle (``start`` / ``stop`` / ``status``), messaging (``send``),
    observation (``subscribe`` / ``get_snapshot``) delegate to a backend chosen
    from the logic.  ``id`` / ``system`` / ``parent`` / ``children`` add the
    actor-model addressing and tree the backend has no concept of.
    """

    def __init__(
        self,
        logic: ActorLogic,
        *,
        id: str | None = None,
        clock: Clock | None = None,
        system: ActorSystem | None = None,
        parent: Actor | None = None,
        input: Any = None,
    ) -> None:
        self._system = system if system is not None else ActorSystem()
        self._id = id if id is not None else self._system._next_id()
        self._parent = parent
        self._clock = clock
        self._input = input
        self._children: dict[str, Actor] = {}
        # invocation id -> child actor spawned by an `invoke:` on a state
        self._invoked: dict[str, Actor] = {}
        self._invocation_sub: SubscriptionProtocol | None = None
        self._syncing = False
        self._backend: ActorBackend = _build_backend(self, logic, clock, input)
        self._system._register(self)

    # -- identity -----------------------------------------------------------

    @property
    def id(self) -> str:
        return self._id

    @property
    def system(self) -> ActorSystem:
        return self._system

    @property
    def parent(self) -> Actor | None:
        return self._parent

    @property
    def children(self) -> dict[str, Actor]:
        return dict(self._children)

    # -- lifecycle ----------------------------------------------------------

    @property
    def status(self) -> str:
        return self._backend.status

    def start(self, initial_state: State | None = None) -> Actor:
        if self._backend.status == STOPPED:
            # Match XState: a stopped actor does not restart.
            return self
        self._backend.start(initial_state)
        # For machine actors that declare any `invoke:`, reconcile child actors
        # on every state change (the immediate subscribe call handles the
        # initial state). Invoke-free machines skip this entirely.
        if (
            self._backend.is_machine
            and getattr(self._backend, "has_invoke", False)
            and self._invocation_sub is None
        ):
            self._invocation_sub = self._backend.subscribe(
                lambda _snapshot: self._sync_invocations()
            )
        return self

    def stop(self) -> Actor:
        if self._backend.status == STOPPED:
            return self
        # Stop children (including invoked ones) before tearing down self.
        for child in list(self._children.values()):
            child.stop()
        self._children.clear()
        self._invoked.clear()
        if self._invocation_sub is not None:
            self._invocation_sub.unsubscribe()
            self._invocation_sub = None
        self._backend.stop()
        if self._parent is not None:
            self._parent._children.pop(self.id, None)
        self._system._unregister(self)
        return self

    # -- messaging ----------------------------------------------------------

    def send(self, event: object) -> ActorSnapshotValue:
        """Deliver *event* to this actor (run-to-completion for machines)."""
        self._backend.send(event)
        return self.get_snapshot()

    def subscribe(self, listener: Callable[[Any], None]) -> SubscriptionProtocol:
        """Observe snapshot changes. Returns a subscription with ``unsubscribe``."""
        return self._backend.subscribe(listener)

    # -- snapshot -----------------------------------------------------------

    def get_snapshot(self) -> ActorSnapshotValue:
        """Return the current snapshot (XState v5 ``actor.getSnapshot()``)."""
        return self._backend.snapshot

    @property
    def state(self) -> ActorSnapshotValue:
        """Alias for :meth:`get_snapshot`."""
        return self._backend.snapshot

    # -- actor tree ---------------------------------------------------------

    def spawn(
        self,
        logic: ActorLogic,
        *,
        id: str | None = None,
        input: Any = None,
        clock: Clock | None = None,
    ) -> Actor:
        """Create a child actor from *logic* in this actor's system.

        The child is registered as a child of this actor and shares the system,
        but is not started — call :meth:`Actor.start` on the returned actor.
        """
        child = Actor(
            logic,
            id=id,
            clock=clock if clock is not None else self._clock,
            system=self._system,
            parent=self,
            input=input,
        )
        self._children[child.id] = child
        return child

    # -- invoke reconciliation ----------------------------------------------

    def _sync_invocations(self) -> None:
        """Start/stop ``invoke:`` child actors to match the configuration.

        Reconciliation mirrors the interpreter's ``_sync_delays``: invocations
        on states still active are left running, invocations on exited states
        are stopped, and newly entered invocations are spawned and started.
        Runs to a fixed point so that a child resolving synchronously (which can
        transition this actor again) is reconciled within one call.
        """
        if not self._backend.is_machine or self._syncing:
            return
        self._syncing = True
        try:
            while self._reconcile_invocations_once():
                pass
        finally:
            self._syncing = False

    def _reconcile_invocations_once(self) -> bool:
        backend = cast(_MachineBackend, self._backend)
        configuration = backend.snapshot.configuration
        wanted: dict[str, dict] = {}
        for node in configuration:
            for invocation in getattr(node, "invoke", []):
                wanted[invocation["id"]] = invocation

        changed = False

        # Stop invocations whose state is no longer active.
        for inv_id in list(self._invoked):
            if inv_id not in wanted:
                child = self._invoked.pop(inv_id)
                self._children.pop(child.id, None)
                child.stop()
                changed = True

        # Resolve every new invocation's logic + input *before* spawning any, so
        # a bad `src` (e.g. unregistered name) fails atomically rather than
        # leaving earlier invocations of the same pass half-started.
        pending = []
        for inv_id, invocation in wanted.items():
            if inv_id in self._invoked:
                continue
            logic = self._resolve_src(invocation["src"])
            input_value = self._resolve_input(invocation.get("input"))
            pending.append((inv_id, logic, input_value))

        # Start newly entered invocations.
        for inv_id, logic, input_value in pending:
            child = self.spawn(logic, id=inv_id, input=input_value)
            self._invoked[inv_id] = child
            child.subscribe(self._make_invoke_listener(inv_id))
            child.start()
            changed = True

        return changed

    def _resolve_src(self, src: Any) -> ActorLogic:
        """Resolve an invoke ``src`` to actor logic.

        A logic object (Machine / promise / callback logic) is used directly; a
        string is looked up in the machine's ``actors`` registry.
        """
        if isinstance(src, (Machine, PromiseLogic, CallbackLogic, ObservableLogic)):
            return src
        if isinstance(src, str):
            backend = cast(_MachineBackend, self._backend)
            machine = backend.interpreter.machine
            actors = getattr(machine, "actors", {}) or {}
            if src in actors:
                return cast(ActorLogic, actors[src])
            raise ValueError(
                f"Actor logic '{src}' is not registered. "
                f"Pass it via Machine(config, actors={{'{src}': logic}})."
            )
        raise TypeError(f"Unsupported invoke src: {src!r}")

    def _resolve_input(self, input_spec: Any) -> Any:
        if callable(input_spec):
            from xstate.algorithm import _invoke

            state = cast(_MachineBackend, self._backend).snapshot
            return _invoke(input_spec, state.context, getattr(state, "event", None))
        return input_spec

    def _make_invoke_listener(self, inv_id: str) -> Callable[[Any], None]:
        """Feed a child actor's completion back to this actor as an event."""
        sent = {"done": False}

        def listener(snapshot: Any) -> None:
            if sent["done"]:
                return
            status = getattr(snapshot, "status", None)
            if status == "done":
                sent["done"] = True
                self.send(
                    Event(f"done.invoke.{inv_id}", getattr(snapshot, "output", None))
                )
            elif status == "error":
                sent["done"] = True
                self.send(
                    Event(f"error.platform.{inv_id}", getattr(snapshot, "error", None))
                )

        return listener

    def __repr__(self) -> str:
        return f"<Actor id={self._id!r} status={self.status!r}>"


def create_actor(
    logic: ActorLogic,
    *,
    id: str | None = None,
    clock: Clock | None = None,
    system: ActorSystem | None = None,
    input: Any = None,
) -> Actor:
    """Create an :class:`Actor` from actor *logic* (XState v5 ``createActor``).

    *logic* is a :class:`~xstate.machine.Machine`, :func:`from_promise` logic, or
    :func:`from_callback` logic.  The actor is not started; call
    :meth:`Actor.start`.  If no *system* is given a fresh one is created and
    owned by this actor.
    """
    return Actor(logic, id=id, clock=clock, system=system, input=input)


def to_promise(actor: Actor) -> asyncio.Future[Any]:
    """Adapt *actor* to an :class:`asyncio.Future` (XState v5 ``toPromise``).

    The future resolves with the actor's ``output`` when its snapshot reaches
    ``status == "done"``, or raises its ``error`` when it reaches
    ``status == "error"``.  If the actor is already settled the future resolves
    immediately; otherwise it resolves on the next settling snapshot.  Must be
    called with a running event loop.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        raise RuntimeError(
            "to_promise() requires a running event loop; await it inside an "
            "async context, e.g. within asyncio.run(...)."
        ) from None

    future: asyncio.Future[Any] = loop.create_future()

    def _settle(snapshot: Any) -> None:
        if future.done():
            return
        status = getattr(snapshot, "status", None)
        if status == "done":
            future.set_result(getattr(snapshot, "output", None))
        elif status == "error":
            error = getattr(snapshot, "error", None)
            future.set_exception(
                error if isinstance(error, BaseException) else RuntimeError(str(error))
            )

    snapshot = actor.get_snapshot()
    if getattr(snapshot, "status", None) in ("done", "error"):
        _settle(snapshot)
        return future

    subscription = actor.subscribe(_settle)
    future.add_done_callback(lambda _f: subscription.unsubscribe())
    return future

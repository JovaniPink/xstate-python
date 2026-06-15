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

Synchronous-resolution note: this layer runs on the synchronous
:class:`~xstate.interpreter.Interpreter`.  A :func:`from_promise` actor's
function is therefore called eagerly on ``start`` and resolves immediately;
true deferred/asyncio resolution is the remaining 0.5.0 async milestone.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, List, Literal, Optional

from xstate.event import Event
from xstate.interpreter import NOT_STARTED, RUNNING, STOPPED, Interpreter
from xstate.machine import Machine
from xstate.scheduler import Clock
from xstate.state import State

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


def from_promise(fn: Callable[..., Any]) -> PromiseLogic:
    """Create promise actor logic from ``fn`` (XState v5 ``fromPromise``)."""
    return PromiseLogic(fn)


def from_callback(fn: Callable[..., Any]) -> CallbackLogic:
    """Create callback actor logic from ``fn`` (XState v5 ``fromCallback``)."""
    return CallbackLogic(fn)


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
        output: Optional[Any] = None,
        error: Optional[Any] = None,
        context: Optional[Any] = None,
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

    def __init__(self, listeners: set, listener: Callable[[Any], None]):
        self._listeners = listeners
        self._listener: Optional[Callable[[Any], None]] = listener

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

    def __init__(self, actor: "Actor", input: Any):
        self._actor = actor
        self._input = input
        self._listeners: set = set()
        self._snapshot = ActorSnapshot("active")
        self._status = NOT_STARTED

    @property
    def status(self) -> str:
        return self._status

    @property
    def snapshot(self) -> ActorSnapshot:
        return self._snapshot

    def subscribe(self, listener: Callable[[ActorSnapshot], None]):
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

    def __init__(self, actor: "Actor", machine: Machine, clock: Optional[Clock]):
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

    def start(self, initial_state: Optional[State] = None) -> None:
        self.interpreter.start(initial_state)

    def stop(self) -> None:
        self.interpreter.stop()

    def send(self, event) -> Any:
        return self.interpreter.send(event)

    def subscribe(self, listener: Callable[[State], None]):
        return self.interpreter.subscribe(listener)


class _PromiseBackend(_ListenerBackend):
    """Backs an actor with :func:`from_promise` logic."""

    def __init__(self, actor: "Actor", logic: PromiseLogic, input: Any):
        super().__init__(actor, input)
        self._fn = logic.fn

    def start(self, initial_state: Optional[State] = None) -> None:
        if self._status != NOT_STARTED:
            return
        self._status = RUNNING
        try:
            result = _call_with_supported_kwargs(self._fn, input=self._input)
            self._snapshot = ActorSnapshot("done", output=result)
        except Exception as exc:  # noqa: BLE001 - surfaced as actor error
            self._snapshot = ActorSnapshot("error", error=exc)
        self._notify()

    def stop(self) -> None:
        self._status = STOPPED
        self._listeners.clear()

    def send(self, event) -> ActorSnapshot:
        # Promise actors ignore incoming events.
        return self._snapshot


class _CallbackBackend(_ListenerBackend):
    """Backs an actor with :func:`from_callback` logic."""

    def __init__(self, actor: "Actor", logic: CallbackLogic, input: Any):
        super().__init__(actor, input)
        self._fn = logic.fn
        self._receivers: List[Callable[[Any], None]] = []
        self._cleanup: Optional[Callable[[], None]] = None

    def start(self, initial_state: Optional[State] = None) -> None:
        if self._status != NOT_STARTED:
            return
        self._status = RUNNING

        def send_back(event) -> None:
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

    def send(self, event) -> ActorSnapshot:
        for handler in list(self._receivers):
            handler(event)
        return self._snapshot


def _build_backend(actor: "Actor", logic, clock: Optional[Clock], input: Any):
    if isinstance(logic, Machine):
        return _MachineBackend(actor, logic, clock)
    if isinstance(logic, PromiseLogic):
        return _PromiseBackend(actor, logic, input)
    if isinstance(logic, CallbackLogic):
        return _CallbackBackend(actor, logic, input)
    raise TypeError(
        "create_actor expects a Machine, from_promise(...), or from_callback(...) "
        f"logic, got {type(logic).__name__}."
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
        self._actors: Dict[str, "Actor"] = {}
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

    def _register(self, actor: "Actor") -> None:
        actor_id = actor.id
        if actor_id in self._actors and self._actors[actor_id] is not actor:
            raise ValueError(
                f"An actor with id '{actor_id}' is already registered in this system."
            )
        self._actors[actor_id] = actor

    def _unregister(self, actor: "Actor") -> None:
        actor_id = actor.id
        if self._actors.get(actor_id) is actor:
            del self._actors[actor_id]

    def get(self, actor_id: str) -> Optional["Actor"]:
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
        logic,
        *,
        id: Optional[str] = None,
        clock: Optional[Clock] = None,
        system: Optional[ActorSystem] = None,
        parent: Optional["Actor"] = None,
        input: Any = None,
    ):
        self._system = system if system is not None else ActorSystem()
        self._id = id if id is not None else self._system._next_id()
        self._parent = parent
        self._clock = clock
        self._input = input
        self._children: Dict[str, "Actor"] = {}
        # invocation id -> child actor spawned by an `invoke:` on a state
        self._invoked: Dict[str, "Actor"] = {}
        self._invocation_sub = None
        self._syncing = False
        self._backend = _build_backend(self, logic, clock, input)
        self._system._register(self)

    # -- identity -----------------------------------------------------------

    @property
    def id(self) -> str:
        return self._id

    @property
    def system(self) -> ActorSystem:
        return self._system

    @property
    def parent(self) -> Optional["Actor"]:
        return self._parent

    @property
    def children(self) -> Dict[str, "Actor"]:
        return dict(self._children)

    # -- lifecycle ----------------------------------------------------------

    @property
    def status(self) -> str:
        return self._backend.status

    def start(self, initial_state: Optional[State] = None) -> "Actor":
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

    def stop(self) -> "Actor":
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

    def send(self, event) -> Any:
        """Deliver *event* to this actor (run-to-completion for machines)."""
        self._backend.send(event)
        return self.get_snapshot()

    def subscribe(self, listener: Callable[[Any], None]):
        """Observe snapshot changes. Returns a subscription with ``unsubscribe``."""
        return self._backend.subscribe(listener)

    # -- snapshot -----------------------------------------------------------

    def get_snapshot(self) -> Any:
        """Return the current snapshot (XState v5 ``actor.getSnapshot()``)."""
        return self._backend.snapshot

    @property
    def state(self) -> Any:
        """Alias for :meth:`get_snapshot`."""
        return self._backend.snapshot

    # -- actor tree ---------------------------------------------------------

    def spawn(
        self,
        logic,
        *,
        id: Optional[str] = None,
        input: Any = None,
        clock: Optional[Clock] = None,
    ) -> "Actor":
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
        configuration = self._backend.snapshot.configuration
        wanted: Dict[str, dict] = {}
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

    def _resolve_src(self, src):
        """Resolve an invoke ``src`` to actor logic.

        A logic object (Machine / promise / callback logic) is used directly; a
        string is looked up in the machine's ``actors`` registry.
        """
        if isinstance(src, (Machine, PromiseLogic, CallbackLogic)):
            return src
        if isinstance(src, str):
            machine = self._backend.interpreter.machine
            actors = getattr(machine, "actors", {}) or {}
            if src in actors:
                return actors[src]
            raise ValueError(
                f"Actor logic '{src}' is not registered. "
                f"Pass it via Machine(config, actors={{'{src}': logic}})."
            )
        raise TypeError(f"Unsupported invoke src: {src!r}")

    def _resolve_input(self, input_spec):
        if callable(input_spec):
            from xstate.algorithm import _invoke

            state = self._backend.snapshot
            return _invoke(input_spec, state.context, getattr(state, "event", None))
        return input_spec

    def _make_invoke_listener(self, inv_id: str) -> Callable[[Any], None]:
        """Feed a child actor's completion back to this actor as an event."""
        sent = {"done": False}

        def listener(snapshot) -> None:
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
    logic,
    *,
    id: Optional[str] = None,
    clock: Optional[Clock] = None,
    system: Optional[ActorSystem] = None,
    input: Any = None,
) -> Actor:
    """Create an :class:`Actor` from actor *logic* (XState v5 ``createActor``).

    *logic* is a :class:`~xstate.machine.Machine`, :func:`from_promise` logic, or
    :func:`from_callback` logic.  The actor is not started; call
    :meth:`Actor.start`.  If no *system* is given a fresh one is created and
    owned by this actor.
    """
    return Actor(logic, id=id, clock=clock, system=system, input=input)

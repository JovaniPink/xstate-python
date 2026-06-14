"""Actor model foundation (0.5.0).

XState v5 reframes a running machine as an **actor**: a live unit with an
address (``id``), a mailbox (``send``), an observable snapshot, and membership
in an **actor system**.  ``create_actor(logic)`` replaces ``interpret(machine)``
as the v5 entry point.

This module lands the foundation:

* :class:`ActorSystem` — a registry that every actor belongs to; actors are
  reachable by id via :meth:`ActorSystem.get`.
* :class:`Actor` — a running instance of *actor logic*.  For machine logic it
  wraps the existing :class:`~xstate.interpreter.Interpreter`, exposing the v5
  surface (``id``, ``send``, ``start``, ``stop``, ``subscribe``,
  ``get_snapshot``, ``system``).
* :func:`create_actor` — build an actor from machine logic.

Still to come in 0.5.0 (tracked, not yet implemented here):

* ``from_promise`` / ``from_callback`` actor logic and the asyncio event loop,
* spawned child actors and the parent/child actor tree,
* ``invoke:`` wiring so a state can run a child actor for its lifetime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional

from xstate.interpreter import STOPPED, Interpreter, Subscription
from xstate.machine import Machine
from xstate.scheduler import Clock
from xstate.state import State

if TYPE_CHECKING:
    from typing import Callable


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
        """Generate an id for an actor created without an explicit one."""
        self._anonymous_count += 1
        return f"x:{self._anonymous_count - 1}"

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

    For machine logic this is a thin v5-facing wrapper over
    :class:`~xstate.interpreter.Interpreter`: lifecycle and event delivery
    delegate to the interpreter, while ``id`` and ``system`` add the actor
    addressing that the interpreter has no concept of.
    """

    def __init__(
        self,
        machine: Machine,
        *,
        id: Optional[str] = None,
        clock: Optional[Clock] = None,
        system: Optional[ActorSystem] = None,
    ):
        self._system = system if system is not None else ActorSystem()
        self._id = id if id is not None else self._system._next_id()
        self._interpreter = Interpreter(machine, clock=clock)
        self._system._register(self)

    # -- identity (read-only to keep registry consistent) -------------------

    @property
    def id(self) -> str:
        return self._id

    @property
    def system(self) -> ActorSystem:
        return self._system

    # -- lifecycle ----------------------------------------------------------

    @property
    def status(self) -> str:
        return self._interpreter.status

    def start(self, initial_state: Optional[State] = None) -> "Actor":
        if self._interpreter.status == STOPPED:
            return self
        self._interpreter.start(initial_state)
        return self

    def stop(self) -> "Actor":
        self._interpreter.stop()
        self._system._unregister(self)
        return self

    # -- messaging ----------------------------------------------------------

    def send(self, event) -> State:
        """Deliver *event* to this actor's machine (run-to-completion)."""
        return self._interpreter.send(event)

    def subscribe(self, listener: Callable[[State], None]) -> Subscription:
        """Observe snapshot changes. Returns a subscription with ``unsubscribe``."""
        return self._interpreter.subscribe(listener)

    # -- snapshot -----------------------------------------------------------

    def get_snapshot(self) -> State:
        """Return the current snapshot (XState v5 ``actor.getSnapshot()``)."""
        return self._interpreter.state

    @property
    def state(self) -> State:
        """Alias for :meth:`get_snapshot` (matches Interpreter.state)."""
        return self._interpreter.state

    def __repr__(self) -> str:
        return f"<Actor id={self._id!r} status={self._interpreter._status!r}>"


def create_actor(
    logic: Machine,
    *,
    id: Optional[str] = None,
    clock: Optional[Clock] = None,
    system: Optional[ActorSystem] = None,
) -> Actor:
    """Create an :class:`Actor` from machine *logic* (XState v5 ``createActor``).

    The actor is not started; call :meth:`Actor.start`.  If no *system* is
    given a fresh one is created and owned by this actor.
    """
    return Actor(logic, id=id, clock=clock, system=system)

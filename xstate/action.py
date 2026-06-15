from typing import Any, Callable, Dict, Optional, Union

# Action type markers used internally by the engine.
ASSIGN_TYPE = "xstate.assign"
RAISE_TYPE = "xstate:raise"
SEND_TYPE = "xstate.send"
CANCEL_TYPE = "xstate.cancel"
SEND_PARENT_TYPE = "xstate.send_parent"
SEND_TO_TYPE = "xstate.send_to"

# Action types handled by the interpreter, not the algorithm — passed through
# _get_actions without resolution so the interpreter can act on them.
INTERPRETER_TYPES = {SEND_TYPE, CANCEL_TYPE, SEND_PARENT_TYPE, SEND_TO_TYPE}


class Action:
    type: str
    exec: Optional[Callable[[], None]]
    data: Dict[str, Any]

    def __init__(
        self,
        type: Union[str, Callable[..., Any]],
        exec: Optional[Callable[[], None]] = None,
        data: Optional[Dict[str, Any]] = None,
    ):
        self.type = type
        self.exec = exec
        self.data = data if data is not None else {}

    def __repr__(self):
        return repr({"type": self.type})


def build_action(raw: Any, registry: Optional[Dict[str, Any]] = None) -> Action:
    """Normalise one raw action spec from a config into an :class:`Action`.

    A spec is one of:

    - a **callable** — an inline side-effect; stored as the action's ``type``
      and invoked later by the interpreter / ``state.actions``;
    - a **dict** produced by an action creator (``assign``/``raise_``/``send``/
      ``send_parent``/``send_to``/``cancel``) — used directly via its ``type``;
    - a **string name** — looked up in ``registry`` (the machine's ``actions``).
      If the name resolves to an action-creator dict it is expanded to that
      dict's real type *now*, so the SCXML engine applies it in declared order
      (an ``assign`` runs as an assign, a ``raise_`` is queued, a ``send`` is
      handed to the interpreter) rather than being deferred and mis-ordered.
      Names that resolve to a callable, or that are unregistered, keep the name
      and are resolved later by ``Machine._get_actions``.
    """
    if isinstance(raw, str):
        impl = (registry or {}).get(raw)
        if isinstance(impl, dict) and "type" in impl:
            return Action(impl["type"], data=impl)
        return Action(raw)
    if callable(raw):
        return Action(raw)
    # An inline action-creator dict, e.g. assign({...}) / send("EVT").
    return Action(raw.get("type"), data=raw)


def assign(assignment):
    """Create an ``assign`` action that updates a machine's ``context``.

    ``assignment`` is either:

    - a callable ``(context, event) -> dict`` returning the updates to merge, or
    - a dict mapping context keys to either a static value or a callable
      ``(context, event) -> value``.

    Example::

        from xstate import assign

        increment = assign({"count": lambda ctx, ev: ctx["count"] + 1})
        reset = assign({"count": 0})
        merge = assign(lambda ctx, ev: {"count": ctx["count"] + ev.data["by"]})
    """
    return {"type": ASSIGN_TYPE, "assignment": assignment}


def raise_(event: str) -> Dict[str, str]:
    """Queue an internal event to be processed after the current microstep.

    The event fires within the same macrostep (run-to-completion step), so
    no external ``send()`` or clock tick is needed — it behaves like a
    synchronous internal transition trigger.

    Example::

        from xstate import Machine, raise_

        machine = Machine({
            "initial": "a",
            "states": {
                "a": {"on": {"GO": {"target": "b", "actions": [raise_("PING")]}}},
                "b": {"on": {"PING": "c"}},
                "c": {},
            },
        })
        state = machine.initial_state
        state = machine.transition(state, "GO")
        assert state.value == "c"   # PING fired in the same macrostep
    """
    return {"type": RAISE_TYPE, "event": event}


def send(
    event: Union[str, Dict[str, Any]],
    delay: Optional[float] = None,
    id: Optional[str] = None,
) -> Dict[str, Any]:
    """Send an event from within an action, optionally after a delay.

    Without a delay the event is queued immediately (run-to-completion) via
    the interpreter. With a delay the interpreter schedules it through the
    active :class:`~xstate.scheduler.Clock`; a named ``id`` lets you cancel it.

    Example::

        from xstate import Machine, send, cancel

        machine = Machine({
            "initial": "idle",
            "states": {
                "idle": {
                    "on": {
                        "START": {
                            "target": "waiting",
                            "actions": [send("TIMEOUT", delay=5000, id="t1")],
                        }
                    }
                },
                "waiting": {"on": {"DONE": "success", "TIMEOUT": "failure"}},
                "success": {},
                "failure": {},
            },
        })
    """
    return {"type": SEND_TYPE, "event": event, "delay": delay, "id": id}


def send_parent(
    event: Union[str, Dict[str, Any]],
    delay: Optional[float] = None,
    id: Optional[str] = None,
) -> Dict[str, Any]:
    """Send an event from a child actor to its parent (XState ``sendParent``).

    Only meaningful for an actor that was spawned or invoked by another actor;
    if the actor has no parent the action is a no-op.  Routed by the interpreter
    through the actor system, so it requires running via ``create_actor`` (not a
    bare ``interpret``).

    Example::

        from xstate import send_parent

        # In an invoked child machine, notify the parent it is ready:
        {"entry": [send_parent("CHILD_READY")]}
    """
    return {"type": SEND_PARENT_TYPE, "event": event, "delay": delay, "id": id}


def send_to(
    target: str,
    event: Union[str, Dict[str, Any]],
    delay: Optional[float] = None,
    id: Optional[str] = None,
) -> Dict[str, Any]:
    """Send an event to another actor in the same system by id (``sendTo``).

    ``target`` is the id of an actor registered in this actor's system; if no
    such actor exists the action is a no-op.  Requires running via
    ``create_actor`` so the actor system is available.

    Example::

        from xstate import send_to

        # Forward a request to a sibling "logger" actor:
        {"actions": [send_to("logger", {"type": "LOG", "msg": "hi"})]}
    """
    return {
        "type": SEND_TO_TYPE,
        "target": target,
        "event": event,
        "delay": delay,
        "id": id,
    }


def cancel(send_id: str) -> Dict[str, str]:
    """Cancel a previously-scheduled :func:`send` by its ``id``.

    Has no effect if the send already fired or was never scheduled.

    Example::

        from xstate import Machine, send, cancel

        # Cancel the timer scheduled in the "waiting" entry action:
        cancel("t1")
    """
    return {"type": CANCEL_TYPE, "sendid": send_id}

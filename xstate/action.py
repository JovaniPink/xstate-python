from typing import Any, Callable, Dict, Optional, Union

# Action type markers used internally by the engine.
ASSIGN_TYPE = "xstate.assign"
RAISE_TYPE = "xstate:raise"
SEND_TYPE = "xstate.send"
CANCEL_TYPE = "xstate.cancel"

# Action types handled by the interpreter, not the algorithm — passed through
# _get_actions without resolution so the interpreter can act on them.
INTERPRETER_TYPES = {SEND_TYPE, CANCEL_TYPE}


class Action:
    type: str
    exec: Optional[Callable[[], None]]
    data: Dict[str, Any]

    def __init__(
        self,
        type: str,
        exec: Optional[Callable[[], None]] = None,
        data: Dict[str, Any] = {},
    ):
        self.type = type
        self.exec = exec
        self.data = data

    def __repr__(self):
        return repr({"type": self.type})


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


def cancel(send_id: str) -> Dict[str, str]:
    """Cancel a previously-scheduled :func:`send` by its ``id``.

    Has no effect if the send already fired or was never scheduled.

    Example::

        from xstate import Machine, send, cancel

        # Cancel the timer scheduled in the "waiting" entry action:
        cancel("t1")
    """
    return {"type": CANCEL_TYPE, "sendid": send_id}

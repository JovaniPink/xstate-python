from typing import Callable, Optional, Dict, Any

# Action type markers used internally by the engine.
ASSIGN_TYPE = "xstate.assign"


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

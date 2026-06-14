#!/usr/bin/env python3
"""A data-fetch machine with retry/backoff — showcasing the 0.5.0 actor model.

Where ``traffic_intersection.py`` is a pure control-flow chart loaded from JSON,
this example shows the pieces that need Python: **invoked actors**, **context**,
and **assign**. These can't live in a JSON file because they carry live
callables, so the machine is written as a Python ``dict`` (still the XState
shape) and run through ``create_actor`` — XState v5's entry point.

What it demonstrates:

* ``invoke:`` runs a child actor for the lifetime of the ``loading`` state;
* :func:`~xstate.from_promise` turns a plain function into actor logic that
  resolves to ``done.invoke.<id>`` (``onDone``) or ``error.platform.<id>``
  (``onError``);
* ``input`` is derived from ``context`` and handed to the promise;
* :func:`~xstate.assign` records the result / error / retry count in context;
* a named **guard** (``canRetry``) decides whether a failure retries or gives up;
* a **delayed** transition (``after``) implements backoff between attempts.

Run it::

    python docs/examples/fetch_with_retry.py
"""

from xstate import Machine, assign, create_actor, from_promise
from xstate.scheduler import SimulatedClock

# A flaky data source: fails the first two attempts, then succeeds. Stands in
# for a real network call inside the invoked promise actor.
_ATTEMPTS = {"n": 0}


def fetch_user(input):
    """Promise logic. ``input`` is whatever the invoke's ``input`` resolves to."""
    _ATTEMPTS["n"] += 1
    attempt = _ATTEMPTS["n"]
    print(f"   [fetch] attempt {attempt} for user {input['user_id']!r}")
    if attempt < 3:
        raise RuntimeError("503 Service Unavailable")
    return {"id": input["user_id"], "name": "Ada Lovelace"}


def can_retry(context, event):
    """Guard: keep retrying until we hit the cap."""
    return context["retries"] < context["max_retries"]


machine = Machine(
    {
        "id": "fetcher",
        "initial": "idle",
        "context": {
            "user_id": 42,
            "data": None,
            "error": None,
            "retries": 0,
            "max_retries": 3,
        },
        "states": {
            "idle": {"on": {"FETCH": "loading"}},
            "loading": {
                "invoke": {
                    "id": "getUser",
                    "src": "fetchUser",
                    # input is derived from context and passed to the promise
                    "input": lambda ctx, ev: {"user_id": ctx["user_id"]},
                    "onDone": {
                        "target": "success",
                        "actions": [assign({"data": lambda c, e: e.data})],
                    },
                    "onError": {
                        "target": "retrying",
                        "actions": [
                            assign(
                                {
                                    "error": lambda c, e: str(e.data),
                                    "retries": lambda c, e: c["retries"] + 1,
                                }
                            )
                        ],
                    },
                },
            },
            "retrying": {
                "always": [
                    {"target": "failure", "cond": "exhausted"},
                ],
                # Back off, then try again — but only while canRetry holds.
                "after": {"backoff": {"target": "loading", "cond": "canRetry"}},
            },
            "success": {"type": "final"},
            "failure": {"type": "final"},
        },
    },
    guards={
        "canRetry": can_retry,
        "exhausted": lambda c, e: c["retries"] >= c["max_retries"],
    },
    delays={"backoff": 1000},
    actors={"fetchUser": from_promise(fetch_user)},
)


def main() -> None:
    clock = SimulatedClock()
    actor = create_actor(machine, clock=clock).start()

    def show(label: str) -> None:
        snap = actor.get_snapshot()
        print(f"{label:<22} value={snap.value!r} retries={snap.context['retries']}")

    show("initial")
    actor.send("FETCH")
    show("FETCH (attempt 1)")

    # Each backoff tick retries the fetch; the third attempt succeeds.
    clock.increment(1000)
    show("after backoff #1")
    clock.increment(1000)
    show("after backoff #2")

    snap = actor.get_snapshot()
    print(f"\nfinal value : {snap.value}")
    print(f"loaded data : {snap.context['data']}")
    actor.stop()


if __name__ == "__main__":
    main()

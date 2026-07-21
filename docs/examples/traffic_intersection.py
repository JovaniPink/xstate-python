#!/usr/bin/env python3
"""Run the traffic-intersection statechart defined in ``traffic_intersection.json``.

This showcases xstate-python's headline feature: **a statechart authored as
plain XState JSON** (the same shape you'd export from the Stately.ai editor or
share with a JavaScript codebase) is loaded with ``json.load`` and run directly.

The JSON is fully declarative. Everything that needs Python — the named guards,
entry actions, and delay durations — is supplied at construction time through
the ``guards=``, ``actions=``, and ``delays=`` registries, keyed by the string
names used in the JSON. Nothing about the machine's structure lives in Python.

The machine itself is non-trivial:

* a **parallel** ``operational`` state with three independent regions
  (``northSouth``, ``eastWest``, ``pedestrian``) that advance on their own clocks;
* **delayed transitions** (``after``) using *named* delays so timing is a
  configuration concern, not hard-coded in the chart;
* a **guarded** pedestrian request (``PED_REQUEST`` only crosses when
  ``crossingIsClear``);
* a global **EMERGENCY** override that interrupts every region at once, with
  ``CLEAR`` resuming normal operation.

Run it::

    python docs/examples/traffic_intersection.py

A :class:`~xstate.scheduler.SimulatedClock` is used so time is deterministic:
``clock.increment(ms)`` fires exactly the timers that are due, with no real
waiting — ideal for tests and reproducible demos.
"""

import json
import os

from xstate import HandlerArgs, Machine, interpret
from xstate.scheduler import SimulatedClock

HERE = os.path.dirname(os.path.abspath(__file__))


# --- implementations referenced by name from the JSON -----------------------

# Delay durations (ms). Named in the JSON's `after:` blocks, resolved here so
# timing can be tuned (e.g. shorter cycles during off-peak) without touching
# the chart.
DELAYS = {
    "nsGreen": 6000,
    "ewGreen": 6000,
    "trafficYellow": 2000,
    "nsRed": 8000,
    "ewRed": 8000,
    "walkTime": 5000,
    "flashTime": 3000,
}


def crossing_is_clear(_args: HandlerArgs) -> bool:
    """Guard for `PED_REQUEST`: allow the walk signal only when it is safe.

    A real controller would consult sensor data through ``HandlerArgs.event``;
    here we always allow it.
    """
    return True


def report_all_red(_args: HandlerArgs) -> None:
    print("   [action] all signals -> RED (emergency)")


def start_walk_signal(_args: HandlerArgs) -> None:
    print("   [action] WALK signal illuminated")


ACTIONS = {"allRed": report_all_red, "startWalkSignal": start_walk_signal}


def build_machine() -> Machine:
    with open(os.path.join(HERE, "traffic_intersection.json")) as f:
        config = json.load(f)
    return Machine(
        config,
        actions=ACTIONS,
        guards={"crossingIsClear": crossing_is_clear},
        delays=DELAYS,
    )


def main() -> None:
    machine = build_machine()
    clock = SimulatedClock()
    service = interpret(machine, clock=clock).start()

    def show(label: str) -> None:
        print(f"{label:<24} {service.state.value}")

    show("initial")

    # northSouth runs its green -> yellow -> red cycle on its own timers while
    # eastWest and pedestrian sit idle.
    clock.increment(6000)
    show("after 6s (ns green->)")
    clock.increment(2000)
    show("after +2s (ns yellow->)")

    # A pedestrian presses the button; the guard passes, so the walk region
    # advances independently of the vehicle lights.
    service.send("PED_REQUEST")
    show("PED_REQUEST")
    clock.increment(5000)
    show("after +5s (walk->flash)")

    # An emergency vehicle approaches: one event interrupts every region.
    service.send("EMERGENCY")
    show("EMERGENCY")

    # All clear — normal operation resumes from the top of the cycle.
    service.send("CLEAR")
    show("CLEAR")

    service.stop()


if __name__ == "__main__":
    main()
